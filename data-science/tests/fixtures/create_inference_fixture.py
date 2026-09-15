from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from credit_risk.dataset import FEATURES


CATEGORICAL_FEATURES = [
    "district_id",
    "statement_frequency",
]

NUMERIC_FEATURES = [
    feature
    for feature in FEATURES
    if feature not in CATEGORICAL_FEATURES
]


def create_input() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "account_id": [900001, 900002, 900003, 900004, 900005, 900006],
            "observation_date": pd.to_datetime(["1998-01-31"] * 6),
            "loan_age_months": [6, 12, 18, 24, 30, 36],
            "loan_amount": [50000.0, 75000.0, 120000.0, 180000.0, 250000.0, 400000.0],
            "loan_duration": [12, 24, 36, 48, 60, 60],
            "scheduled_payment": [4200.0, 3200.0, 3600.0, 4100.0, 4800.0, 7200.0],
            "current_balance": [30000.0, 18000.0, 6000.0, 2000.0, 500.0, 100.0],
            "balance_mean_3m": [32000.0, 20000.0, 8000.0, 2500.0, 700.0, 200.0],
            "balance_min_3m": [28000.0, 16000.0, 5000.0, 1500.0, 200.0, 50.0],
            "balance_change_3m": [3000.0, 1000.0, -500.0, -1500.0, -3000.0, np.nan],
            "credit_sum_3m": [30000.0, 24000.0, 18000.0, 12000.0, 8000.0, 5000.0],
            "withdrawal_sum_3m": [22000.0, 21000.0, 19000.0, 15000.0, 12000.0, 9000.0],
            "net_flow_3m": [8000.0, 3000.0, -1000.0, -3000.0, -4000.0, -4000.0],
            "transaction_count_3m": [45, 38, 30, 24, 18, 12],
            "sanction_count_3m": [0, 0, 0, 1, 2, 3],
            "loan_payment_sum_3m": [12600.0, 9600.0, 9000.0, 7000.0, 4000.0, 1000.0],
            "current_payment_ratio": [1.0, 1.0, 0.83, 0.57, 0.28, 0.05],
            "district_id": [1, 1, 2, 2, 3, 99],
            "statement_frequency": ["POPLATEK MESICNE", "POPLATEK MESICNE", "POPLATEK TYDNE", "POPLATEK TYDNE", "POPLATEK PO OBRATU", "UNKNOWN"],
        }
    )


def create_model(frame: pd.DataFrame) -> Pipeline:
    numeric_pipeline = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy="median",
                    add_indicator=True,
                ),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore"),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        [
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    model = Pipeline(
        [
            (
                "preprocess",
                preprocessor,
            ),
            (
                "model",
                LogisticRegression(
                    random_state=42,
                    max_iter=1000,
                ),
            ),
        ]
    )

    target = np.array([0, 0, 0, 1, 1, 1])

    model.fit(
        frame[FEATURES],
        target,
    )

    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    frame = create_input()
    model = create_model(frame)

    args.model.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.input.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    bundle = {
        "model": model,
        "features": FEATURES,
        "threshold": 0.5,
        "dataset_id": "synthetic-ci-fixture",
        "feature_pipeline_version": "ci-test",
    }

    joblib.dump(
        bundle,
        args.model,
    )

    frame.to_parquet(
        args.input,
        index=False,
    )

    print(f"Modelo sintético: {args.model}")
    print(f"Entrada sintética: {args.input}")
    print(f"Filas: {len(frame)}")


if __name__ == "__main__":
    main()
