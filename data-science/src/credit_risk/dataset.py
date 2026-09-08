from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import ARTIFACTS, DATA, config, write_json

FEATURES = [
 "loan_age_months","loan_amount","loan_duration","scheduled_payment","current_balance",
 "balance_mean_3m","balance_min_3m","balance_change_3m","credit_sum_3m","withdrawal_sum_3m",
 "net_flow_3m","transaction_count_3m","sanction_count_3m","loan_payment_sum_3m",
 "current_payment_ratio","district_id","statement_frequency"]

def _load_transactions(root: Path) -> pd.DataFrame:
    files=sorted(root.glob("period=*/data.parquet"))
    if not files: raise FileNotFoundError(f"No released partitions in {root}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

def build_dataset(source_root: Path | None=None, allow_archive: bool=True) -> pd.DataFrame:
    source_root = source_root or DATA / "raw_archive" / "transactions"
    if not allow_archive and "raw_archive" in source_root.parts:
        raise PermissionError("Production feature pipeline cannot read raw_archive")
    tx=_load_transactions(source_root).sort_values(["account_id","date","trans_id"])
    monthly=(tx.groupby(["account_id","period"],as_index=False)
      .agg(current_balance=("balance","last"), balance_mean=("balance","mean"),
           balance_min=("balance","min"), credit_sum=("amount",lambda s: s[tx.loc[s.index,"is_credit"]].sum()),
           withdrawal_sum=("amount",lambda s: s[tx.loc[s.index,"is_withdrawal"]].sum()),
           transaction_count=("trans_id","size"), sanction_count=("is_sanction_interest","sum"),
           loan_payment_sum=("amount",lambda s: s[tx.loc[s.index,"is_loan_payment"]].sum())))
    monthly.sort_values(["account_id","period"],inplace=True)
    g=monthly.groupby("account_id",group_keys=False)
    for col in ["balance_mean","balance_min","credit_sum","withdrawal_sum","transaction_count","sanction_count","loan_payment_sum"]:
        monthly[f"{col}_3m"] = g[col].rolling(3,min_periods=1).sum().reset_index(level=0,drop=True) if col not in ["balance_mean","balance_min"] else (
          g[col].rolling(3,min_periods=1).mean().reset_index(level=0,drop=True) if col=="balance_mean" else g[col].rolling(3,min_periods=1).min().reset_index(level=0,drop=True))
    monthly["balance_change_3m"]=monthly.current_balance-g.current_balance.shift(3)
    monthly["net_flow_3m"]=monthly.credit_sum_3m-monthly.withdrawal_sum_3m
    reference=(DATA/"raw_archive") if allow_archive else (DATA/"incoming"/"reference")
    loan=pd.read_parquet(reference/"loan.parquet")
    account=pd.read_parquet(reference/"account.parquet")
    out=monthly.merge(loan,on="account_id",how="inner",suffixes=("","_loan")).merge(account[["account_id","district_id","frequency"]],on="account_id")
    out=out[out.period.ge(out.date)].copy()
    out["loan_age_months"]=(out.period.dt.year-out.date.dt.year)*12+(out.period.dt.month-out.date.dt.month)
    out.rename(columns={"amount":"loan_amount","duration":"loan_duration","payments":"scheduled_payment","frequency":"statement_frequency"},inplace=True)
    out["current_payment_ratio"]=out.loan_payment_sum_3m/(3*out.scheduled_payment).replace(0,np.nan)
    # First negative balance is the observable severe-distress event.
    first_bad=monthly.loc[monthly.balance_min.lt(0)].groupby("account_id").period.min()
    out["event_date"]=out.account_id.map(first_bad)
    horizon=out.period+pd.offsets.MonthEnd(config()["label_horizon_months"])
    out["label_maturity_date"]=horizon
    out["target"]=(out.event_date.gt(out.period)&out.event_date.le(horizon)).astype(int)
    # At-risk population only; observations after distress are invalid.
    out=out[out.event_date.isna()|out.period.lt(out.event_date)]
    out["is_mature"]=out.label_maturity_date.le(tx.period.max())
    out["observation_date"]=out.period
    out["data_available_date"]=out.period
    return out

def build_and_save() -> dict:
    out=build_dataset()
    (DATA/"features").mkdir(parents=True,exist_ok=True); (DATA/"labels").mkdir(parents=True,exist_ok=True)
    out[["account_id","observation_date",*FEATURES]].to_parquet(DATA/"features"/"snapshots.parquet",index=False)
    out[["account_id","observation_date","event_date","label_maturity_date","is_mature","target"]].to_parquet(DATA/"labels"/"labels.parquet",index=False)
    out.to_parquet(DATA/"modeling_dataset.parquet",index=False)
    meta={"rows":len(out),"accounts":out.account_id.nunique(),"period_min":str(out.period.min().date()),"period_max":str(out.period.max().date()),"mature_rows":int(out.is_mature.sum()),"events":int(out.loc[out.is_mature,"target"].sum())}
    write_json(DATA/"modeling_dataset_manifest.json",meta); return meta

def build_incoming_features() -> dict:
    out=build_dataset(DATA/"incoming"/"transactions",allow_archive=False)
    latest=out.observation_date.max(); frame=out[out.observation_date.eq(latest)]
    path=DATA/"features"/f"production-{latest:%Y-%m}.parquet"; path.parent.mkdir(parents=True,exist_ok=True)
    frame[["account_id","observation_date",*FEATURES]].to_parquet(path,index=False)
    return {"period":str(latest.date()),"rows":len(frame),"path":str(path)}
