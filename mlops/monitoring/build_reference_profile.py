"""Build the reference profile used by the daily drift job.

The profile describes the training split of the champion: decile edges and
bucket shares per feature and for the score. It contains aggregates only,
never rows. Upload it to ``monitoring/reference/profile.json`` in the data
bucket.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from credit_risk.common import ARTIFACTS, DATA
from credit_risk.modeling import split
from mlops.monitoring.quality import build_profile

CATEGORICAL = {"district_id", "statement_frequency"}


def reference_profile(dataset_path: Path, model_path: Path) -> dict:
    bundle = joblib.load(model_path)
    return profile_from(split(pd.read_parquet(dataset_path))["train"], bundle)


def profile_from(train: pd.DataFrame, bundle: dict) -> dict:
    features = bundle["features"]
    frame = train[features].astype(object).where(train[features].notna(), None)
    columns = {name: frame[name].tolist() for name in features}
    columns["score"] = bundle["model"].predict_proba(train[features])[:, 1].tolist()
    source = f"train split of {bundle['dataset_id']}, threshold {float(bundle['threshold'])}"
    return build_profile(columns, CATEGORICAL, source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATA / "modeling_dataset.parquet")
    parser.add_argument("--model", type=Path, default=ARTIFACTS / "champion.joblib")
    parser.add_argument("--output", type=Path, default=Path("dist/monitoring/profile.json"))
    args = parser.parse_args()
    profile = reference_profile(args.dataset, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "rows": profile["rows"], "features": len(profile["features"])}))
