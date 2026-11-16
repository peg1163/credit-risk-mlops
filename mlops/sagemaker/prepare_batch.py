"""Convert one monthly feature Parquet into SageMaker JSON Lines input."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path

import joblib
import pandas as pd


def prepare_batch(input_path: Path, output_path: Path, model_path: Path, period: str) -> dict:
    from credit_risk.sagemaker_serve import validate_records

    try:
        year, month = map(int, period.split("-"))
        date(year, month, 1)
        if len(period) != 7:
            raise ValueError
    except ValueError:
        raise ValueError("Period must be YYYY-MM") from None

    bundle = joblib.load(model_path)
    frame = pd.read_parquet(input_path)
    required = ["account_id", "observation_date", *bundle["features"]]
    if frame.empty:
        raise ValueError("Batch input is empty")
    if set(frame.columns) != set(required):
        raise ValueError(f"Batch columns differ from the model contract: {sorted(set(required) ^ set(frame.columns))}")
    if frame[["account_id", "observation_date"]].duplicated().any():
        raise ValueError("Duplicate account and observation date")
    records = []
    for row in frame[required].to_dict(orient="records"):
        record = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                value = value.date().isoformat()
            elif value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value)):
                value = None
            elif hasattr(value, "item"):
                value = value.item()
                if isinstance(value, float) and not math.isfinite(value):
                    value = None
            record[key] = value
        records.append(record)
    validated = validate_records(records, bundle["features"])
    if not validated.observation_date.str.startswith(period).all():
        raise ValueError("Input contains observations outside the requested period")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as target:
        for record in records:
            target.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
    payload = output_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    manifest = {
        "period": period,
        "batch_id": digest[:16],
        "rows": len(records),
        "input_file": output_path.name,
        "input_sha256": digest,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "dataset_id": bundle["dataset_id"],
        "feature_pipeline_version": bundle["feature_pipeline_version"],
        "model_version": "0.1.0",
        "endpoint_example_file": f"endpoint-example-{period}.json",
    }
    output_path.with_name(manifest["endpoint_example_file"]).write_text(json.dumps(records[0], indent=2) + "\n")
    output_path.with_suffix(output_path.suffix + ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--model", type=Path, default=Path("data-science/artifacts/champion.joblib"))
    args = parser.parse_args()
    print(json.dumps(prepare_batch(args.input, args.output, args.model, args.period), indent=2))
