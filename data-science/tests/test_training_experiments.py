from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from credit_risk.common import DATA
from credit_risk.sagemaker_serve import load_bundle
from mlops.experiments import retraining
from mlops.sagemaker import start_training_job, train


@pytest.fixture(scope="module")
def dataset():
    return pd.read_parquet(DATA / "modeling_dataset.parquet")


def test_challenger_only_learns_labels_known_at_the_retraining_date(dataset):
    as_of = pd.Timestamp("1997-07-31")
    parts = retraining.challenger_parts(dataset, as_of, validation_months=12)
    assert parts["all"].label_maturity_date.max() <= as_of
    assert parts["validation"].observation_date.min() == pd.Timestamp("1996-02-29")
    assert parts["train"].observation_date.max() < parts["validation"].observation_date.min()


def test_paired_bootstrap_of_identical_models_shows_no_difference():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 300)
    p = rng.random(300)
    result = retraining.paired_bootstrap(y, p, p, samples=50, seed=1)
    assert result["roc_auc"]["delta"] == 0 and result["roc_auc"]["ci95"] == [0.0, 0.0]
    assert retraining.verdict(result) == "no_significant_difference"


def test_verdict_needs_the_whole_interval_on_one_side():
    assert retraining.verdict({"roc_auc": {"ci95": [0.01, 0.05]}}) == "challenger_better"
    assert retraining.verdict({"roc_auc": {"ci95": [-0.05, -0.01]}}) == "challenger_worse"
    assert retraining.verdict({"roc_auc": {"ci95": [-0.01, 0.05]}}) == "no_significant_difference"


def test_psi_noise_floor_grows_with_buckets_and_small_months():
    ten = {"proportions": {str(i): 0.1 for i in range(10)}}
    assert retraining.psi_noise_floor(ten, 100, 1000) == pytest.approx(9 * (1 / 100 + 1 / 1000))
    assert retraining.psi_noise_floor(ten, 500, 1000) < retraining.psi_noise_floor(ten, 100, 1000)


def test_simulation_report_keeps_structural_drift_apart(dataset, tmp_path):
    report = retraining.run(DATA / "modeling_dataset.parquet", dates=("1998-01-31",), samples=30)
    window = report["retraining"]["windows"][0]
    assert window["evaluation"] == ["1998-02-28", "1998-06-30"]
    assert window["challenger"]["label_cutoff"] == "1997-07-31"
    months = report["drift"]
    assert months[0]["month"] == "1996-01" and months[-1]["month"] == "1998-12"
    assert all(month["psi_max_feature"] not in retraining.STRUCTURAL_FEATURES for month in months)
    assert "loan_age_months" in months[0]["psi"]
    assert "| 1998-01-31 |" in retraining.summary(report)


@pytest.fixture
def ml_root(tmp_path, monkeypatch):
    channel = tmp_path / "input/data/training"
    channel.mkdir(parents=True)
    (channel / train.DATASET_FILE).write_bytes((DATA / "modeling_dataset.parquet").read_bytes())
    for name, path in {"HYPERPARAMETERS": "input/config/hyperparameters.json", "CHANNEL": "input/data/training",
                       "MODEL_DIR": "model", "OUTPUT_DATA": "output/data", "FAILURE": "output/failure"}.items():
        monkeypatch.setattr(train, name, tmp_path / path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", (tmp_path / "mlruns").as_uri())
    monkeypatch.setenv("TRAINING_JOB_NAME", "test-job")
    return tmp_path


def write_hyperparameters(root, values: dict):
    path = root / "input/config/hyperparameters.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values))


def test_training_job_writes_a_model_the_endpoint_can_serve(ml_root):
    write_hyperparameters(ml_root, {"mode": "train", "train_end": "1995-06-30"})
    assert train.main() == 0
    bundle = load_bundle(ml_root / "model")
    manifest = json.loads((ml_root / "model/manifest.json").read_text())
    assert manifest["training_job_name"] == "test-job" and manifest["splits"]["train_end"] == "1995-06-30"
    assert manifest["mlflow_run_id"]
    assert 0 < bundle["threshold"] < 1


def test_training_job_reports_unknown_mode_as_failure(ml_root):
    write_hyperparameters(ml_root, {"mode": "deploy"})
    assert train.main() == 1
    assert "Unknown mode 'deploy'" in (ml_root / "output/failure").read_text()


class FakeSageMaker:
    def __init__(self):
        self.created = None

    def create_training_job(self, **body):
        self.created = body

    def describe_training_job(self, TrainingJobName):
        return {"TrainingJobStatus": "Completed", "SecondaryStatus": "Completed", "BillableTimeInSeconds": 95,
                "ModelArtifacts": {"S3ModelArtifacts": f"s3://bucket/models/training-jobs/{TrainingJobName}/output/model.tar.gz"}}


def test_launcher_builds_the_job_with_the_mlflow_app_and_waits(capsys):
    client = FakeSageMaker()
    code = start_training_job.main([
        "--image", "123.dkr.ecr.us-east-1.amazonaws.com/repo@sha256:abc", "--role-arn", "arn:aws:iam::123:role/r",
        "--bucket", "bucket", "--mlflow-app-arn", "arn:aws:sagemaker:us-east-1:123:mlflow-app/app-X",
        "--mode", "retraining-simulation", "--hyperparameter", "bootstrap_samples=50", "--spot", "--wait",
    ], sagemaker=client)
    body = client.created
    assert code == 0
    assert body["Environment"]["MLFLOW_TRACKING_URI"] == "arn:aws:sagemaker:us-east-1:123:mlflow-app/app-X"
    assert body["HyperParameters"] == {"mode": "retraining-simulation", "bootstrap_samples": "50"}
    assert body["InputDataConfig"][0]["DataSource"]["S3DataSource"]["S3Uri"] == "s3://bucket/datasets/modeling/pkdd99-berka-sha256-75ab2f39/"
    assert body["OutputDataConfig"]["S3OutputPath"] == "s3://bucket/models/training-jobs/"
    assert body["EnableManagedSpotTraining"] and body["StoppingCondition"]["MaxWaitTimeInSeconds"] == 7200
    assert len(body["TrainingJobName"]) <= 63
    assert '"model_artifact_key": "models/training-jobs/' in capsys.readouterr().out
