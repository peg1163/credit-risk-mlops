"""Retrospective performance of the endpoint once six-month labels mature.

Joins the real accepted capture lines with mature labels by
``(account_id, observation_date)`` and compares ROC-AUC, KS, Brier and recall
with the thresholds of ``docs/MONITORING_AND_RETRAINING.md``. Runs locally or
in a job; it needs the scientific dependencies, not the Lambda runtime.

    aws s3 sync s3://<bucket>/endpoint-capture/ dist/endpoint-capture/
    PYTHONPATH=data-science/src:. python mlops/monitoring/retrospective.py \
        --capture-dir dist/endpoint-capture --labels data-science/data/labels/labels.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import brier_score_loss, recall_score, roc_auc_score

from credit_risk.modeling import ks

BRIER_REFERENCE = 0.0449
THRESHOLDS = {
    "roc_auc_min": 0.75,
    "ks_min": 0.30,
    "brier_max": BRIER_REFERENCE * 1.25,
    "recall_min": 0.15,
}


def load_capture(capture_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(capture_dir.rglob("*.jsonl")):
        for text in path.read_text().splitlines():
            line = json.loads(text)
            if line.get("synthetic") or line.get("status") != "accepted":
                continue
            rows.append(
                {
                    "account_id": line["output"]["account_id"],
                    "observation_date": pd.Timestamp(line["output"]["observation_date"]),
                    "score": line["output"]["score"],
                    "decision": line["output"]["decision"],
                    "model_version": line["output"]["model_version"],
                    "captured_at": line["captured_at"],
                }
            )
    frame = pd.DataFrame(rows, columns=["account_id", "observation_date", "score", "decision", "model_version", "captured_at"])
    # The same account and date scored twice counts once, with its latest score.
    return frame.sort_values("captured_at").drop_duplicates(["account_id", "observation_date"], keep="last")


def evaluate(capture: pd.DataFrame, labels: pd.DataFrame) -> dict:
    mature = labels[labels.is_mature][["account_id", "observation_date", "target"]]
    joined = capture.merge(mature, on=["account_id", "observation_date"], how="inner")
    result = {
        "captured_records": int(len(capture)),
        "labeled_records": int(len(joined)),
        "events": int(joined.target.sum()) if len(joined) else 0,
        "thresholds": THRESHOLDS,
        "cohorts": {},
    }
    for period, cohort in joined.groupby(joined.observation_date.dt.strftime("%Y-%m")):
        metrics = {"rows": int(len(cohort)), "events": int(cohort.target.sum())}
        if cohort.target.nunique() == 2:
            metrics.update(
                roc_auc=float(roc_auc_score(cohort.target, cohort.score)),
                ks=float(ks(cohort.target, cohort.score)),
                brier=float(brier_score_loss(cohort.target, cohort.score)),
                recall=float(recall_score(cohort.target, cohort.decision, zero_division=0)),
            )
            metrics["alerts"] = [
                name
                for name, failed in {
                    "roc_auc": metrics["roc_auc"] < THRESHOLDS["roc_auc_min"],
                    "ks": metrics["ks"] < THRESHOLDS["ks_min"],
                    "brier": metrics["brier"] > THRESHOLDS["brier_max"],
                    "recall": metrics["recall"] < THRESHOLDS["recall_min"],
                }.items()
                if failed
            ]
        else:
            metrics["alerts"] = ["single_class_cohort"]
        result["cohorts"][period] = metrics
    low_recall = [period for period, metrics in result["cohorts"].items() if "recall" in metrics["alerts"]]
    # Recall needs two mature cohorts below the threshold before it counts.
    result["recall_alert"] = len(low_recall) >= 2
    result["investigate"] = result["recall_alert"] or any(
        alert in {"roc_auc", "ks", "brier"} for metrics in result["cohorts"].values() for alert in metrics["alerts"]
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/monitoring/retrospective.json"))
    args = parser.parse_args()
    labels = pd.read_parquet(args.labels)
    labels["observation_date"] = pd.to_datetime(labels.observation_date)
    report = evaluate(load_capture(args.capture_dir), labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "labeled_records": report["labeled_records"], "investigate": report["investigate"]}))
