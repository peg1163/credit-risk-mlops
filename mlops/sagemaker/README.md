# SageMaker inference package (local preparation)

The full architecture, deployment sequence, S3 layout, monitoring plan and
cleanup checklist are in [`docs/SAGEMAKER_HANDOFF.md`](../../docs/SAGEMAKER_HANDOFF.md).

This package reuses champion v0.1.0. It predicts the first negative account
balance within six months for **existing loan accounts with known features**.
It is an educational proxy, not an applicant credit score or a lending decision.

## Build without AWS access

Run from the repository root with the project virtual environment active:

```bash
python mlops/sagemaker/package_model.py
PYTHONPATH=data-science/src python mlops/sagemaker/prepare_batch.py \
  --input data-science/data/features/production-1998-01.parquet \
  --period 1998-01 \
  --output dist/sagemaker/features-1998-01.jsonl
docker build -f mlops/docker/sagemaker-inference.Dockerfile -t credit-risk-sagemaker:0.1.0 .
```

The generated `dist/` directory is ignored by Git. Upload `model.tar.gz` to
private S3 storage. Push the image to your private ECR repository. A SageMaker
model references both the ECR image and the S3 `model.tar.gz` URL. SageMaker
extracts the archive into `/opt/ml/model` inside the container.

To test the image locally:

```bash
docker run --rm -p 8080:8080 \
  -v "$PWD/data-science/artifacts:/opt/ml/model:ro" \
  credit-risk-sagemaker:0.1.0 serve
```

Then send one JSON object to `POST http://localhost:8080/invocations` with
`Content-Type: application/json`, or one JSON object per line with
`Content-Type: application/jsonlines`. `GET /ping` checks readiness.
`prepare_batch.py` creates `endpoint-example-1998-01.json` for the single-record
test and a `.manifest.json` next to the batch file.
Each object contains `account_id`, a month-end `observation_date` in
`YYYY-MM-DD`, and all 17 features in `docs/DATA_DICTIONARY.md`. Numeric values
may be `null` only where the trained model's imputer is needed. Missing fields,
unexpected fields and non-finite numbers are rejected.

## Batch Transform configuration

- Input S3 URI: `features/period=YYYY-MM/batch_id=<id>/features.jsonl`.
- Input content type: `application/jsonlines`.
- Split type: `Line`; output accept: `application/jsonlines`; assemble with `Line`.
- Start with one instance and one concurrent transform for the small sample.
- Output S3 URI: `predictions/period=YYYY-MM/batch_id=<id>/`.
- Upload the generated `.manifest.json` beside the input. The output file has
  a `.out` suffix. Verify its row count and match its account IDs to the input.

The JSON Lines output contains `account_id`, `observation_date`, `score`,
`decision`, `model_version`, `dataset_id`, and `feature_pipeline_version`.
The model's `decision` threshold is scientific only and is not a business cutoff.

## Real-time endpoint

Use `Content-Type: application/json` with exactly one record. The endpoint
returns one JSON result. **The endpoint does not automatically persist its
response**: the calling application must store the input ID, output, timestamp,
model version and request ID in S3 if audit storage is desired. For a learning
lab, delete the endpoint after testing to stop serving charges.

No AWS resources or credentials are created by these local scripts.

## AWS handoff checklist

1. Choose the correct account and Region. Create a private ECR repository and
   push the tested image. Record its immutable digest.
2. Upload `model.tar.gz` to a private, versioned S3 prefix and record its object
   version and SHA-256. Upload the JSON Lines batch and manifest under the
   chosen `period` and `batch_id` prefix.
3. Create a SageMaker execution role with read access to the model and feature
   input prefixes, write access to the prediction prefix, and the necessary ECR
   and CloudWatch Logs permissions. Keep raw future data and labels inaccessible
   to inference.
4. Create a SageMaker Model using the ECR image digest and the S3 model archive.
   Run Batch Transform with the format settings above; inspect the `.out` file.
5. Create an endpoint configuration and endpoint from the same SageMaker Model.
   Invoke it using the generated example request, compare its score with the
   corresponding batch output, and delete the endpoint after the exercise.
6. Keep the feature input, prediction output, manifest, model version, image
   digest and job ID together for later monitoring and audit.
