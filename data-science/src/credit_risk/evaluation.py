from __future__ import annotations
import joblib, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from .common import ARTIFACTS, DATA, write_json
from .dataset import FEATURES
from .modeling import split, ks

def evaluate():
    df=pd.read_parquet(DATA/"modeling_dataset.parquet"); model=joblib.load(ARTIFACTS/"champion.joblib")["model"]
    test=split(df)["test"].copy(); test["score"]=model.predict_proba(test[FEATURES])[:,1]
    def group_metrics(g):
      if g.target.nunique()<2: return pd.Series({"rows":len(g),"events":int(g.target.sum()),"roc_auc":None,"pr_auc":None,"brier":brier_score_loss(g.target,g.score),"ks":None,"score_mean":g.score.mean()})
      return pd.Series({"rows":len(g),"events":int(g.target.sum()),"roc_auc":roc_auc_score(g.target,g.score),"pr_auc":average_precision_score(g.target,g.score),"brier":brier_score_loss(g.target,g.score),"ks":ks(g.target,g.score),"score_mean":g.score.mean()})
    by_period=test.groupby(test.observation_date.dt.strftime("%Y-%m")).apply(group_metrics,include_groups=False).to_dict("index")
    test["loan_amount_segment"]=pd.qcut(test.loan_amount,3,duplicates="drop").astype(str)
    by_segment=test.groupby("loan_amount_segment",observed=True).apply(group_metrics,include_groups=False).to_dict("index")
    bins=pd.qcut(test.score,10,duplicates="drop"); calibration=test.groupby(bins,observed=True).agg(rows=("target","size"),mean_score=("score","mean"),event_rate=("target","mean")).reset_index(drop=True).to_dict("records")
    result={"by_period":by_period,"by_loan_amount_segment":by_segment,"calibration_deciles":calibration,"score_quantiles":test.score.quantile([0,.01,.05,.5,.95,.99,1]).to_dict()}
    write_json(ARTIFACTS/"detailed_evaluation.json",result); return result
