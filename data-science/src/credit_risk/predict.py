from __future__ import annotations
import argparse, json
from pathlib import Path
import joblib, pandas as pd
from .common import ARTIFACTS, DATA
def predict(input_path: Path, output_path: Path):
    bundle=joblib.load(ARTIFACTS/"champion.joblib"); df=pd.read_parquet(input_path)
    p=bundle["model"].predict_proba(df[bundle["features"]])[:,1]
    out=df[["account_id","observation_date"]].copy(); out["score"]=p; out["decision"]=(p>=bundle["threshold"]).astype(int); out["model_version"]="0.1.0"; out["dataset_id"]=bundle["dataset_id"]
    output_path.parent.mkdir(parents=True,exist_ok=True); out.to_parquet(output_path,index=False); return {"rows":len(out),"output":str(output_path)}
def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); print(json.dumps(predict(a.input,a.output),indent=2))
if __name__=="__main__": main()

