from __future__ import annotations
import argparse, json, os, subprocess
from pathlib import Path
import joblib, numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score,brier_score_loss,confusion_matrix,precision_score,recall_score,roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from .common import ARTIFACTS, DATA, config, write_json
from .dataset import FEATURES

CAT=["district_id","statement_frequency"]; NUM=[x for x in FEATURES if x not in CAT]
def ks(y,p):
    d=pd.DataFrame({"y":y,"p":p}).sort_values("p",ascending=False); pos=max(d.y.sum(),1); neg=max((1-d.y).sum(),1)
    return float(((d.y.cumsum()/pos)-((1-d.y).cumsum()/neg)).abs().max())
def metrics(y,p,threshold):
    pred=(p>=threshold).astype(int)
    return {"roc_auc":roc_auc_score(y,p),"pr_auc":average_precision_score(y,p),"brier":brier_score_loss(y,p),"ks":ks(y,p),"precision":precision_score(y,pred,zero_division=0),"recall":recall_score(y,pred,zero_division=0),"threshold":threshold,"confusion_matrix":confusion_matrix(y,pred).tolist(),"rows":len(y),"events":int(np.sum(y))}
def split(df):
    c=config()["splits"]
    mature=df[df.is_mature]
    return {"train":mature[mature.observation_date.le(c["train_end"])],"validation":mature[mature.observation_date.between(c["validation_start"],c["validation_end"])],"test":mature[mature.observation_date.between(c["test_start"],c["test_end"])]}
def train():
    df=pd.read_parquet(DATA/"modeling_dataset.parquet"); parts=split(df)
    prep=ColumnTransformer([("num",Pipeline([("imp",SimpleImputer(strategy="median",add_indicator=True)),("scale",StandardScaler())]),NUM),("cat",Pipeline([("imp",SimpleImputer(strategy="most_frequent")),("onehot",OneHotEncoder(handle_unknown="ignore"))]),CAT)])
    model=Pipeline([("preprocess",prep),("model",LogisticRegression(C=0.5,class_weight="balanced",max_iter=2000,random_state=config()["random_seed"]))])
    model.fit(parts["train"][FEATURES],parts["train"].target)
    pv=model.predict_proba(parts["validation"][FEATURES])[:,1]
    thresholds=np.linspace(.05,.95,181); f1=[]
    for t in thresholds:
      pr=precision_score(parts["validation"].target,pv>=t,zero_division=0); re=recall_score(parts["validation"].target,pv>=t,zero_division=0); f1.append(2*pr*re/(pr+re) if pr+re else 0)
    threshold=float(thresholds[int(np.argmax(f1))])
    all_metrics={k:metrics(v.target,model.predict_proba(v[FEATURES])[:,1],threshold) for k,v in parts.items()}
    ARTIFACTS.mkdir(parents=True,exist_ok=True); joblib.dump({"model":model,"features":FEATURES,"threshold":threshold,"dataset_id":config()["dataset_id"],"feature_pipeline_version":config()["feature_pipeline_version"]},ARTIFACTS/"champion.joblib")
    write_json(ARTIFACTS/"metrics.json",all_metrics)
    rows=[]
    for name,part in parts.items():
      q=part[["account_id","observation_date","target"]].copy(); q["score"]=model.predict_proba(part[FEATURES])[:,1]; q["split"]=name; rows.append(q)
    pd.concat(rows).to_parquet(ARTIFACTS/"evaluation_predictions.parquet",index=False)
    try:
      import mlflow
      mlflow.set_tracking_uri((ARTIFACTS/"mlruns").resolve().as_uri()); mlflow.set_experiment("credit-risk-baseline")
      with mlflow.start_run(run_name="logistic-regression-v1"):
        mlflow.log_params({"model":"logistic_regression","C":0.5,"class_weight":"balanced","dataset_id":config()["dataset_id"],"feature_pipeline_version":config()["feature_pipeline_version"],"train_cutoff":config()["splits"]["train_end"]})
        for sp,vals in all_metrics.items():
          for k,v in vals.items():
            if isinstance(v,(int,float)): mlflow.log_metric(f"{sp}_{k}",v)
        from mlflow.models import infer_signature
        example=parts["train"][FEATURES].head(5)
        signature=infer_signature(example,model.predict_proba(example))
        mlflow.log_artifact(str(ARTIFACTS/"metrics.json")); mlflow.sklearn.log_model(model,name="model",signature=signature,input_example=example)
    except ImportError: print("WARNING: MLflow unavailable; model and metrics saved, MLflow run not registered")
    return all_metrics
def main(): print(json.dumps(train(),indent=2))
if __name__=="__main__": main()
