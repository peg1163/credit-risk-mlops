from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


EXPECTED_COLUMNS = {
    "account_id",
    "observation_date",
    "score",
    "decision",
    "model_version",
    "dataset_id",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"No existe la salida: {args.input}")

    frame = pd.read_parquet(args.input)

    if len(frame) != args.expected_rows:
        raise AssertionError(
            f"Se esperaban {args.expected_rows} filas y se obtuvieron {len(frame)}"
        )

    if set(frame.columns) != EXPECTED_COLUMNS:
        raise AssertionError(f"Columnas incorrectas: {list(frame.columns)}")

    if not frame["score"].between(0, 1).all():
        raise AssertionError("Existen scores fuera del rango [0, 1]")

    duplicates = frame.duplicated(["account_id", "observation_date"]).sum()

    if duplicates != 0:
        raise AssertionError(f"Se encontraron {duplicates} duplicados")

    dataset_ids = frame["dataset_id"].unique().tolist()

    if dataset_ids != ["synthetic-ci-fixture"]:
        raise AssertionError(f"Dataset ID inesperado: {dataset_ids}")

    print(f"Filas: {len(frame)}")
    print("Scores válidos: True")
    print("Duplicados: 0")
    print("Dataset ID: synthetic-ci-fixture")


if __name__ == "__main__":
    main()
