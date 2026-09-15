#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-credit-risk-inference:ci}"
FIXTURE_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$FIXTURE_DIR"
}

trap cleanup EXIT

mkdir -p "$FIXTURE_DIR/model" "$FIXTURE_DIR/input" "$FIXTURE_DIR/output"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --entrypoint python \
    --volume "$PROJECT_ROOT/data-science/tests/fixtures:/fixtures-source:ro" \
    --volume "$FIXTURE_DIR:/fixtures" \
    "$IMAGE_NAME" \
    /fixtures-source/create_inference_fixture.py \
    --model /fixtures/model/champion.joblib \
    --input /fixtures/input/input.parquet

MODEL_PATH="$FIXTURE_DIR/model/champion.joblib" \
INPUT_DIR="$FIXTURE_DIR/input" \
OUTPUT_DIR="$FIXTURE_DIR/output" \
IMAGE_NAME="$IMAGE_NAME" \
"$PROJECT_ROOT/mlops/scripts/run-inference.sh" input.parquet predictions.parquet

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --entrypoint python \
    --volume "$PROJECT_ROOT/data-science/tests/fixtures:/fixtures-source:ro" \
    --volume "$FIXTURE_DIR:/fixtures:ro" \
    "$IMAGE_NAME" \
    /fixtures-source/validate_inference_output.py \
    --input /fixtures/output/predictions.parquet \
    --expected-rows 6
