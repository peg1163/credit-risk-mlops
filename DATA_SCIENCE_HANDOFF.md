# Data Science handoff to MLOps

## Delivery

Champion v0.1.0 is a regularized logistic-regression pipeline predicting first negative account balance in the six months after a monthly snapshot for an active loan account. It uses real PKDD'99 Czech bank transactions. This is a severe-distress proxy, not mortgage 90+ DPD, and is exclusively educational.

Freddie Mac was the first choice. On 2026-09-08 its full/per-vintage data required Clarity registration. The directly downloadable Release 47 sample was not relationally usable (zero loan-ID overlap between origination and performance), and legacy endpoints returned 403. The precise evidence and official documentation are retained locally. Freddie Mac states that the full dataset covers mortgages from 1999–2026 and performance through 2026-03, but redistribution is restricted; never commit those raw files.

## Dataset and temporal contract

- Dataset ID: `pkdd99-berka-sha256-75ab2f39`.
- Prepared loan-account history: 191,556 transactions, 682 accounts, 1993-01 to 1998-12, 72 monthly partitions, 5.3 MB Parquet archive.
- Modeling dataset: 16,837 pre-event snapshots, 654 accounts; 13,321 mature labels and 204 positive rows.
- Train through 1995-12; validate 1996; OOT test 1997; simulate production in 1998.
- Observation/inference/data-availability date is month-end. The label matures six month-ends later. Snapshots after the first event are excluded. July–December 1998 labels remain censored at source cutoff.
- Multiple snapshots and overlapping horizons are intentionally retained for monthly scoring; do not interpret rows as independent. Entity-grouped sensitivity/bootstrap analysis is future scientific work.

Feature definitions and null handling are in `docs/DATA_DICTIONARY.md`. The feature pipeline version is `1.0.0`. Direct status and all future/event fields are forbidden.

## Model, execution and metrics

The bundle `data-science/artifacts/champion.joblib` contains preprocessing, estimator, ordered feature list, threshold, dataset ID and feature-pipeline version. Exact dependencies are pinned in `data-science/requirements.txt`. Commands are documented in `data-science/README.md`.

OOT test metrics: ROC-AUC 0.8637, KS 0.6257, PR-AUC 0.0745, Brier 0.0449, precision 0.0923 and recall 0.1875 at threshold 0.75; confusion matrix `[[4401,118],[52,12]]`. Calibration is poor and probabilities must not be treated as calibrated PDs. Full metrics live in `artifacts/metrics.json` and `artifacts/detailed_evaluation.json`.

Local MLflow experiment `credit-risk-baseline` records parameters, split metrics, dataset ID, feature version, train cutoff, model with signature/input example, and metrics artifact under `artifacts/mlruns`. MLOps must additionally attach Git SHA, immutable container digest, environment lockfile, orchestration run ID and S3 object versions.

## Replay contract

Only `credit_risk.replay` reads `data/raw_archive`. It releases a single `period=YYYY-MM/data.parquet`, copies static reference data on first use, verifies SHA-256, creates a batch manifest, advances persistent state and rejects duplicates or backward releases. `--next`, `--release-month`, `--status` and `--reset` are supported. Production feature code reads only `data/incoming`.

Suggested S3 mapping:

- Restricted `s3://.../raw-archive/`: source archive, reference tables and dataset manifest; versioning enabled, replay IAM only.
- `incoming/`: released partitions and reference data; feature-job read access.
- `features/`, `labels/`, `predictions/`: derived versioned outputs.
- `manifests/`: batch/replay audit trail.
- `models/`: champion bundle, signature, requirements, metrics and model card.

Future raw partitions and immature labels must remain inaccessible to inference, monitoring and production feature roles. Labels need a separate IAM prefix/role from inference.

## What MLOps must monitor

Implement the checks and scientific thresholds in `docs/MONITORING_AND_RETRAINING.md`, plus job success, retries, duration, memory, output counts, stale data, manifest mismatch and model-load/inference errors. Preserve lineage: dataset ID, batch ID, observation cutoff, feature version, model version, code SHA and image digest on every prediction batch.

Retraining is considered after enough matured outcomes and sustained degradation, material drift with performance evidence, schema/business change, or scheduled review. Promotion is human-approved champion/challenger; aggregate AUC alone is not sufficient. Rollback must restore model, threshold, feature contract and image together.

## CI/CD evidence required

Run unit/scientific tests, replay integration test, inference-contract test, lint/type/security checks, dependency scan, deterministic small-data training smoke test, Docker build/scan, and artifact checksum verification. Seven tests currently pass locally. Add golden-batch equivalence and container-level tests when images exist.

## Configurable platform parameters and errors

Configure dataset/bucket/prefix IDs, replay start, target horizon, history window, cutoff dates, threshold, model URI, MLflow URI, retry/timeout, log level and dry-run. Handle missing/duplicate/out-of-order batches, partial copy, checksum/schema failure, empty cohorts, unknown categories, censored labels, absent model, incompatible schema and non-finite scores.

## Decisions for the MLOps Engineer

- Choose local-first then S3/EventBridge orchestration; no AWS resources have been created.
- Decide whether replay state belongs in a versioned S3 object (cheapest) or DynamoDB (stronger concurrency).
- Choose batch inference before an always-on API; this dataset is naturally monthly.
- Establish artifact retention, encryption, IAM separation and deletion policy.
- Decide whether to preserve this proxy project or later replace data with a manually licensed Freddie Mac vintage and restore the original 90+ DPD target.
- Choose business threshold/cost matrix only after defining false-positive/false-negative costs; 0.75 is a scientific demo threshold.

