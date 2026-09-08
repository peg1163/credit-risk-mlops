from __future__ import annotations
import argparse, json, shutil
from datetime import date
from pathlib import Path
import pandas as pd
from .common import DATA, config, month_end, parse_berka_date, sha256, write_json

FILES = ["account", "client", "disp", "district", "loan", "trans"]

def prepare(source: Path) -> dict:
    raw = DATA / "raw_archive"
    if raw.exists():
        raise FileExistsError(f"Immutable archive already exists: {raw}; remove explicitly to rebuild")
    raw.mkdir(parents=True)
    tables = {n: pd.read_csv(source / f"{n}.asc", sep=";", low_memory=False) for n in FILES}
    for n in ("account", "loan", "trans"):
        tables[n]["date"] = parse_berka_date(tables[n]["date"])
    loan_ids = set(tables["loan"].account_id)
    tx = tables["trans"].loc[tables["trans"].account_id.isin(loan_ids)].copy()
    tx["period"] = month_end(tx["date"])
    tx["is_credit"] = tx["type"].eq("PRIJEM")
    tx["is_withdrawal"] = tx["type"].eq("VYDAJ")
    tx["is_sanction_interest"] = tx["k_symbol"].eq("SANKC. UROK")
    tx["is_loan_payment"] = tx["k_symbol"].eq("UVER")
    tx.sort_values(["period", "account_id", "date", "trans_id"], inplace=True)
    for period, part in tx.groupby("period"):
        out = raw / "transactions" / f"period={period:%Y-%m}" / "data.parquet"
        out.parent.mkdir(parents=True)
        part.to_parquet(out, index=False)
    for n in ["account", "client", "disp", "district", "loan"]:
        tables[n].to_parquet(raw / f"{n}.parquet", index=False)
    source_hashes = {f"{n}.asc": sha256(source / f"{n}.asc") for n in FILES}
    manifest = {
        "dataset_id": config()["dataset_id"], "source": "PKDD'99 Czech Financial Dataset",
        "source_mirror": "https://github.com/jlacko/berka-dataset",
        "download_date": str(date.today()), "source_hashes": source_hashes,
        "loan_accounts": len(loan_ids), "transaction_rows": len(tx),
        "period_min": str(tx.period.min().date()), "period_max": str(tx.period.max().date()),
        "partitions": tx.period.nunique(), "raw_archive_immutable_by_convention": True,
    }
    write_json(raw / "dataset_manifest.json", manifest)
    sample = tx.groupby("account_id", group_keys=False).head(3).head(200)
    (DATA / "sample").mkdir(parents=True, exist_ok=True)
    sample.to_parquet(DATA / "sample" / "transactions_sample.parquet", index=False)
    return manifest

def main():
    p=argparse.ArgumentParser(); p.add_argument("--source", type=Path, required=True)
    print(json.dumps(prepare(p.parse_args().source), indent=2))
if __name__ == "__main__": main()

