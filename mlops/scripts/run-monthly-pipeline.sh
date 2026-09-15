#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-$PROJECT_ROOT/data-science/data/replay_runtime}"
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/data-science/artifacts/champion.joblib}"
CONFIG_PATH="$PROJECT_ROOT/data-science/configs/project.yaml"

if [[ $# -eq 1 && "$1" == "--next" ]]; then
    REPLAY_ARGS=(--next)
elif [[ $# -eq 2 && "$1" == "--release-month" && "$2" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    REPLAY_ARGS=(--release-month "$2")
else
    echo "Uso: $0 --next | --release-month YYYY-MM" >&2
    exit 2
fi

PRODUCTION_START="$(sed -n 's/^[[:space:]]*production_start:[[:space:]]*"\([0-9][0-9][0-9][0-9]-[0-9][0-9]\)-[0-9][0-9]"[[:space:]]*$/\1/p' "$CONFIG_PATH")"

if [[ -z "$PRODUCTION_START" ]]; then
    echo "No se pudo leer production_start desde: $CONFIG_PATH" >&2
    exit 3
fi

echo "[1/3] Liberando el siguiente batch histórico"
REPLAY_RESULT="$(RUNTIME_DIR="$RUNTIME_DIR" IMAGE_NAME="${REPLAY_IMAGE_NAME:-credit-risk-replay:0.1.0}" "$PROJECT_ROOT/mlops/scripts/run-replay.sh" "${REPLAY_ARGS[@]}")"
printf '%s\n' "$REPLAY_RESULT"

PERIOD="$(printf '%s\n' "$REPLAY_RESULT" | sed -n 's/.*"period": "\([0-9][0-9][0-9][0-9]-[0-9][0-9]\)".*/\1/p')"

if [[ -z "$PERIOD" ]]; then
    echo "El replay no devolvió un periodo válido" >&2
    exit 4
fi

if [[ "$PERIOD" < "$PRODUCTION_START" ]]; then
    echo "Batch $PERIOD liberado como warm-up; la inferencia comienza en $PRODUCTION_START."
    exit 0
fi

echo "[2/3] Construyendo features para $PERIOD"
RUNTIME_DIR="$RUNTIME_DIR" IMAGE_NAME="${FEATURES_IMAGE_NAME:-credit-risk-features:0.1.0}" "$PROJECT_ROOT/mlops/scripts/run-features.sh"

FEATURE_FILE="production-$PERIOD.parquet"
PREDICTION_FILE="predictions-$PERIOD.parquet"

if [[ ! -f "$RUNTIME_DIR/features/$FEATURE_FILE" ]]; then
    echo "No se generó el archivo esperado: $RUNTIME_DIR/features/$FEATURE_FILE" >&2
    exit 5
fi

echo "[3/3] Generando predicciones para $PERIOD"
MODEL_PATH="$MODEL_PATH" INPUT_DIR="$RUNTIME_DIR/features" OUTPUT_DIR="$RUNTIME_DIR/predictions" IMAGE_NAME="${INFERENCE_IMAGE_NAME:-credit-risk-inference:0.1.0}" "$PROJECT_ROOT/mlops/scripts/run-inference.sh" "$FEATURE_FILE" "$PREDICTION_FILE"

if [[ ! -f "$RUNTIME_DIR/predictions/$PREDICTION_FILE" ]]; then
    echo "No se generó el archivo esperado: $RUNTIME_DIR/predictions/$PREDICTION_FILE" >&2
    exit 6
fi

echo "Pipeline mensual completado: $RUNTIME_DIR/predictions/$PREDICTION_FILE"
