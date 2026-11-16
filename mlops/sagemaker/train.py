"""Entrypoint of the SageMaker training image (ADR-0010).

SageMaker runs the container with the argument ``train`` and this layout:

- ``/opt/ml/input/config/hyperparameters.json``: every value is a string.
- ``/opt/ml/input/data/training/``: the ``training`` channel, with
  ``modeling_dataset.parquet``.
- ``/opt/ml/model/``: SageMaker tars it into ``<output>/<job>/output/model.tar.gz``,
  with the same layout as ``package_model.py``, so the endpoint can serve it.
- ``/opt/ml/output/data/``: tarred into ``output.tar.gz`` (reports).
- ``/opt/ml/output/failure``: the reason shown by ``DescribeTrainingJob``.

Hyperparameter ``mode``:

- ``train`` fits a candidate with the configured or given splits.
- ``retraining-simulation`` runs ``mlops/experiments/retraining.py``.

Both log to MLflow. The job sets ``MLFLOW_TRACKING_URI`` to the SageMaker
MLflow App ARN; without it, the run goes to a local store inside the output.
``ML_ROOT`` replaces ``/opt/ml`` to run this outside SageMaker.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get("ML_ROOT", "/opt/ml"))
HYPERPARAMETERS = ROOT / "input/config/hyperparameters.json"
CHANNEL = ROOT / "input/data/training"
MODEL_DIR = ROOT / "model"
OUTPUT_DATA = ROOT / "output/data"
FAILURE = ROOT / "output/failure"
DATASET_FILE = "modeling_dataset.parquet"
SPLIT_KEYS = ("train_end", "validation_start", "validation_end", "test_start", "test_end")


def hyperparameters() -> dict[str, str]:
    return json.loads(HYPERPARAMETERS.read_text()) if HYPERPARAMETERS.exists() else {}


def job_tags() -> dict[str, str]:
    tags = {"runtime": "sagemaker-training" if "TRAINING_JOB_NAME" in os.environ else "local"}
    for env, tag in (("TRAINING_JOB_NAME", "sagemaker.training_job_name"), ("TRAINING_JOB_ARN", "sagemaker.training_job_arn"),
                     ("IMAGE_VERSION", "image_version"), ("DATASET_URI", "dataset_uri")):
        if os.environ.get(env):
            tags[tag] = os.environ[env]
    return tags


def train_candidate(params: dict[str, str]) -> dict:
    from credit_risk.common import config
    from credit_risk.dataset import FEATURES
    from credit_risk.modeling import bundle, fit, metrics, split, tracking_uri
    from credit_risk.sagemaker_serve import MODEL_VERSION
    from mlops.sagemaker.package_model import write_model_dir

    splits = {**config()["splits"], **{key: params[key] for key in SPLIT_KEYS if key in params}}
    C = float(params.get("C", 0.5))
    seed = int(params.get("seed", config()["random_seed"]))
    parts = split(pd.read_parquet(CHANNEL / DATASET_FILE), splits)
    model, threshold = fit(parts, C, seed)
    results = {name: metrics(part.target, model.predict_proba(part[FEATURES])[:, 1], threshold) for name, part in parts.items()}

    run_id = None
    try:
        import mlflow
        from mlflow.models import infer_signature

        mlflow.set_tracking_uri(tracking_uri())
        mlflow.set_experiment(params.get("experiment", "credit-risk-candidates"))
        with mlflow.start_run(run_name=params.get("run_name", f"candidate-train-end-{splits['train_end']}"), tags=job_tags()) as run:
            run_id = run.info.run_id
            mlflow.log_params({"model": "logistic_regression", "C": C, "class_weight": "balanced", "seed": seed,
                               "dataset_id": config()["dataset_id"], "feature_pipeline_version": config()["feature_pipeline_version"],
                               **{f"split_{key}": splits[key] for key in SPLIT_KEYS}})
            for part, values in results.items():
                mlflow.log_metrics({f"{part}_{k}": v for k, v in values.items() if isinstance(v, (int, float))})
            example = parts["train"][FEATURES].head(5)
            mlflow.sklearn.log_model(model, name="model", signature=infer_signature(example, model.predict_proba(example)),
                                     input_example=example)
    except ImportError:
        print("WARNING: MLflow unavailable; model written, run not registered")

    extra = {"training_job_name": os.environ.get("TRAINING_JOB_NAME"), "splits": splits, "mlflow_run_id": run_id}
    manifest = write_model_dir(bundle(model, threshold), MODEL_DIR, MODEL_VERSION, extra)
    OUTPUT_DATA.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DATA / "metrics.json").write_text(json.dumps(results, indent=2, default=float) + "\n")
    return {"mode": "train", "threshold": threshold, "mlflow_run_id": run_id, "model_sha256": manifest["model_sha256"],
            "test_roc_auc": results["test"]["roc_auc"]}


def retraining_simulation(params: dict[str, str]) -> dict:
    from mlops.experiments import retraining

    argv = ["--dataset", str(CHANNEL / DATASET_FILE), "--output-dir", str(OUTPUT_DATA / "retraining")]
    for key, flag in (("retrain_dates", "--retrain-dates"), ("horizon_months", "--horizon-months"),
                      ("validation_months", "--validation-months"), ("C", "--C"),
                      ("bootstrap_samples", "--bootstrap-samples"), ("run_name", "--run-name")):
        if key in params:
            argv += [flag, params[key]]
    if params.get("refit", "true").lower() == "false":
        argv.append("--no-refit")
    report = retraining.main(argv, tags=job_tags())
    policy = report["retraining"]["policy_retrain_every_window_vs_static"]
    return {"mode": "retraining-simulation", "mlflow_run_id": report.get("mlflow_run_id"),
            "policy_verdict": policy["verdict"] if policy else None}


MODES = {"train": train_candidate, "retraining-simulation": retraining_simulation}


def main() -> int:
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        os.environ["MLFLOW_TRACKING_URI"] = (OUTPUT_DATA / "mlruns").resolve().as_uri()
    try:
        params = hyperparameters()
        mode = params.get("mode", "train")
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode!r}; expected one of {sorted(MODES)}")
        print(json.dumps(MODES[mode](params), default=str))
        return 0
    except Exception as error:  # SageMaker shows the failure file as FailureReason
        FAILURE.parent.mkdir(parents=True, exist_ok=True)
        FAILURE.write_text(f"{type(error).__name__}: {error}"[:1000])
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
