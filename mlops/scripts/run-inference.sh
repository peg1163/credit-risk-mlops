#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/data-science/artifacts/champion.joblib}"
INPUT_DIR="${INPUT_DIR:-$PROJECT_ROOT/data-science/data/features}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/data-science/data/predictions}"
IMAGE_NAME="${IMAGE_NAME:-credit-risk-inference:0.1.0}"

if [[ $# -ne 2 ]]; then
    echo "Uso: $0 <archivo-entrada.parquet> <archivo-salida.parquet>" >&2
    exit 2
fi

INPUT_FILE="$1"
OUTPUT_FILE="$2"

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "No existe el modelo: $MODEL_PATH" >&2
    exit 3
fi

if [[ ! -f "$INPUT_DIR/$INPUT_FILE" ]]; then
    echo "No existe la entrada: $INPUT_DIR/$INPUT_FILE" >&2
    exit 4
fi

mkdir -p "$OUTPUT_DIR"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$MODEL_PATH:/app/data-science/artifacts/champion.joblib:ro" \
    --volume "$INPUT_DIR:/app/input:ro" \
    --volume "$OUTPUT_DIR:/app/output" \
    "$IMAGE_NAME" \
    --input "/app/input/$INPUT_FILE" \
    --output "/app/output/$OUTPUT_FILE"
