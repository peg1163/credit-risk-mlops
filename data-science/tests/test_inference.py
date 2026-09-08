from pathlib import Path
import pandas as pd
from credit_risk.common import DATA
from credit_risk.predict import predict
def test_prediction_contract(tmp_path: Path):
    source=pd.read_parquet(DATA/"features"/"snapshots.parquet").head(20); inp=tmp_path/"in.parquet"; out=tmp_path/"out.parquet"; source.to_parquet(inp,index=False)
    result=predict(inp,out); scored=pd.read_parquet(out)
    assert result["rows"]==20 and scored.score.between(0,1).all()
    assert {"account_id","observation_date","score","decision","model_version","dataset_id"}==set(scored.columns)
