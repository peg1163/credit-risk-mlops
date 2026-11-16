"""Start a SageMaker training job with the training image (ADR-0010).

Run it with your own AWS credentials; values come from ``terraform output``
of ``infrastructure/terraform/environments/dev``:

    python mlops/sagemaker/start_training_job.py \\
      --image <training_repository_url>@<digest> \\
      --role-arn <sagemaker_training_role_arn> \\
      --bucket <data_bucket_name> \\
      --mlflow-app-arn <mlflow_app_arn> \\
      --mode retraining-simulation --wait

The dataset must be in ``s3://<bucket>/datasets/modeling/<dataset_id>/``.
The model lands in ``s3://<bucket>/models/training-jobs/<job>/output/model.tar.gz``
and reports in ``.../output/output.tar.gz``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

DATASET_PREFIX = "datasets/modeling"
OUTPUT_PREFIX = "models/training-jobs"
TERMINAL = {"Completed", "Failed", "Stopped"}


def job_name(mode: str, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"credit-risk-{mode}-{stamp}"[:63]


def request(args, name: str, dataset_uri: str) -> dict:
    hyperparameters = {"mode": args.mode, **dict(item.split("=", 1) for item in args.hyperparameter)}
    environment = {"DATASET_URI": dataset_uri}
    if args.mlflow_app_arn:
        environment["MLFLOW_TRACKING_URI"] = args.mlflow_app_arn
    stopping = {"MaxRuntimeInSeconds": args.max_runtime_seconds}
    if args.spot:
        stopping["MaxWaitTimeInSeconds"] = args.max_runtime_seconds * 2
    return {
        "TrainingJobName": name,
        "AlgorithmSpecification": {"TrainingImage": args.image, "TrainingInputMode": "File"},
        "RoleArn": args.role_arn,
        "HyperParameters": hyperparameters,
        "Environment": environment,
        "InputDataConfig": [{
            "ChannelName": "training",
            "DataSource": {"S3DataSource": {"S3DataType": "S3Prefix", "S3Uri": dataset_uri, "S3DataDistributionType": "FullyReplicated"}},
            "ContentType": "application/x-parquet",
        }],
        "OutputDataConfig": {"S3OutputPath": f"s3://{args.bucket}/{OUTPUT_PREFIX}/"},
        "ResourceConfig": {"InstanceType": args.instance_type, "InstanceCount": 1, "VolumeSizeInGB": 5},
        "StoppingCondition": stopping,
        "EnableManagedSpotTraining": args.spot,
        "Tags": [{"Key": "Project", "Value": "credit-risk-mlops"}, {"Key": "Mode", "Value": args.mode}],
    }


def wait(sagemaker, name: str, poll_seconds: int = 30) -> dict:
    last = None
    while True:
        job = sagemaker.describe_training_job(TrainingJobName=name)
        state = (job["TrainingJobStatus"], job.get("SecondaryStatus"))
        if state != last:
            print(f"{datetime.now(timezone.utc):%H:%M:%S} {state[0]} / {state[1]}", flush=True)
            last = state
        if job["TrainingJobStatus"] in TERMINAL:
            return job
        time.sleep(poll_seconds)


def main(argv=None, sagemaker=None) -> int:
    parser = argparse.ArgumentParser(description="Start a SageMaker training job (ADR-0010).")
    parser.add_argument("--image", required=True, help="<training_repository_url>@<digest> or :<tag>")
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--dataset-id", default="pkdd99-berka-sha256-75ab2f39")
    parser.add_argument("--mlflow-app-arn", help="SageMaker MLflow App ARN; without it the run stays inside output.tar.gz")
    parser.add_argument("--mode", choices=["train", "retraining-simulation"], default="train")
    parser.add_argument("--hyperparameter", action="append", default=[], metavar="KEY=VALUE",
                        help="for example train_end=1996-12-31 or bootstrap_samples=2000")
    parser.add_argument("--instance-type", default="ml.m5.large")
    parser.add_argument("--max-runtime-seconds", type=int, default=3600)
    parser.add_argument("--spot", action="store_true", help="managed spot training: cheaper, may wait for capacity")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print the request without calling AWS")
    args = parser.parse_args(argv)

    name = job_name(args.mode)
    dataset_uri = f"s3://{args.bucket}/{DATASET_PREFIX}/{args.dataset_id}/"
    body = request(args, name, dataset_uri)
    if args.dry_run:
        print(json.dumps(body, indent=2))
        return 0
    if sagemaker is None:
        import boto3

        sagemaker = boto3.client("sagemaker")
    sagemaker.create_training_job(**body)
    print(f"Started {name}")
    if not args.wait:
        return 0
    job = wait(sagemaker, name)
    if job["TrainingJobStatus"] != "Completed":
        print(f"FailureReason: {job.get('FailureReason')}", file=sys.stderr)
        return 1
    print(json.dumps({
        "model_artifact": job["ModelArtifacts"]["S3ModelArtifacts"],
        "model_artifact_key": job["ModelArtifacts"]["S3ModelArtifacts"].split("/", 3)[3],
        "billable_seconds": job.get("BillableTimeInSeconds"),
        "training_seconds": job.get("TrainingTimeInSeconds"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
