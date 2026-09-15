from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from create_inference_fixture import create_input, create_model
from credit_risk.dataset import FEATURES


PERIODS = ["1997-10", "1997-11", "1997-12", "1998-01"]
ACCOUNT_IDS = [900001, 900002, 900003, 900004, 900005, 900006]


def create_archive(archive: Path) -> None:
    archive.mkdir(parents=True, exist_ok=True)

    accounts = pd.DataFrame(
        {
            "account_id": ACCOUNT_IDS,
            "district_id": [1, 1, 2, 2, 3, 99],
            "frequency": [
                "POPLATEK MESICNE",
                "POPLATEK MESICNE",
                "POPLATEK TYDNE",
                "POPLATEK TYDNE",
                "POPLATEK PO OBRATU",
                "UNKNOWN",
            ],
        }
    )
    loans = pd.DataFrame(
        {
            "account_id": ACCOUNT_IDS,
            "date": pd.to_datetime(["1997-01-01"] * len(ACCOUNT_IDS)),
            "amount": [50000.0, 75000.0, 120000.0, 180000.0, 250000.0, 400000.0],
            "duration": [12, 24, 36, 48, 60, 60],
            "payments": [4200.0, 3200.0, 3600.0, 4100.0, 4800.0, 7200.0],
        }
    )

    accounts.to_parquet(archive / "account.parquet", index=False)
    loans.to_parquet(archive / "loan.parquet", index=False)

    trans_id = 1
    for month_index, period_text in enumerate(PERIODS):
        period = pd.Period(period_text, freq="M")
        rows = []
        for account_index, account_id in enumerate(ACCOUNT_IDS):
            base_balance = 50000.0 - account_index * 4000.0 + month_index * 500.0
            for day, amount, balance, is_credit, is_withdrawal, is_loan_payment in [
                (5, 10000.0, base_balance + 10000.0, True, False, False),
                (15, 3500.0 + account_index * 100.0, base_balance + 6500.0, False, True, True),
            ]:
                rows.append(
                    {
                        "trans_id": trans_id,
                        "account_id": account_id,
                        "date": pd.Timestamp(period.year, period.month, day),
                        "period": period.to_timestamp("M"),
                        "amount": amount,
                        "balance": balance,
                        "is_credit": is_credit,
                        "is_withdrawal": is_withdrawal,
                        "is_sanction_interest": False,
                        "is_loan_payment": is_loan_payment,
                    }
                )
                trans_id += 1

        destination = archive / "transactions" / f"period={period_text}" / "data.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(destination, index=False)

    manifest = {
        "dataset_id": "pkdd99-berka-sha256-75ab2f39",
        "partitions": len(PERIODS),
        "period_min": PERIODS[0],
        "period_max": PERIODS[-1],
        "synthetic": True,
    }
    (archive / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def create_model_artifact(path: Path) -> None:
    frame = create_input()
    bundle = {
        "model": create_model(frame),
        "features": FEATURES,
        "threshold": 0.5,
        "dataset_id": "synthetic-ci-fixture",
        "feature_pipeline_version": "ci-test",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()

    create_archive(args.archive)
    create_model_artifact(args.model)
    print(f"Archivo histórico sintético: {args.archive}")
    print(f"Modelo sintético: {args.model}")


if __name__ == "__main__":
    main()
