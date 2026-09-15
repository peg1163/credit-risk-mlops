#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_ROOT="$(mktemp -d)"
PYTHON_BIN="${PYTHON_BIN:-python}"
REPLAY_IMAGE="${REPLAY_IMAGE:-credit-risk-replay:ci}"
FEATURES_IMAGE="${FEATURES_IMAGE:-credit-risk-features:ci}"
INFERENCE_IMAGE="${INFERENCE_IMAGE:-credit-risk-inference:ci}"
trap 'rm -rf "$FIXTURE_ROOT"' EXIT

ARCHIVE_DIR="$FIXTURE_ROOT/raw_archive"
RUNTIME_DIR="$FIXTURE_ROOT/replay_runtime"
MODEL_PATH="$FIXTURE_ROOT/model/champion.joblib"

PYTHONPATH="$PROJECT_ROOT/data-science/src" "$PYTHON_BIN" "$PROJECT_ROOT/data-science/tests/fixtures/create_monthly_pipeline_fixture.py" --archive "$ARCHIVE_DIR" --model "$MODEL_PATH"

for expected_period in 1997-10 1997-11 1997-12; do
    output="$(ARCHIVE_DIR="$ARCHIVE_DIR" RUNTIME_DIR="$RUNTIME_DIR" MODEL_PATH="$MODEL_PATH" REPLAY_IMAGE_NAME="$REPLAY_IMAGE" FEATURES_IMAGE_NAME="$FEATURES_IMAGE" INFERENCE_IMAGE_NAME="$INFERENCE_IMAGE" "$PROJECT_ROOT/mlops/scripts/run-monthly-pipeline.sh" --next)"
    printf '%s\n' "$output"
    grep -q "Batch $expected_period liberado como warm-up" <<< "$output"
done

ARCHIVE_DIR="$ARCHIVE_DIR" RUNTIME_DIR="$RUNTIME_DIR" MODEL_PATH="$MODEL_PATH" REPLAY_IMAGE_NAME="$REPLAY_IMAGE" FEATURES_IMAGE_NAME="$FEATURES_IMAGE" INFERENCE_IMAGE_NAME="$INFERENCE_IMAGE" "$PROJECT_ROOT/mlops/scripts/run-monthly-pipeline.sh" --next

PYTHONPATH="$PROJECT_ROOT/data-science/src" "$PYTHON_BIN" "$PROJECT_ROOT/data-science/tests/fixtures/validate_inference_output.py" --input "$RUNTIME_DIR/predictions/predictions-1998-01.parquet" --expected-rows 6

test -f "$RUNTIME_DIR/manifests/batch-1998-01.json"
test -f "$RUNTIME_DIR/features/production-1998-01.parquet"

echo "Monthly pipeline integration test: OK"
