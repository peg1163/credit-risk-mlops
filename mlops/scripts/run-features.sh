#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-credit-risk-features:0.1.0}"
RUNTIME_DIR="${RUNTIME_DIR:-$PROJECT_ROOT/data-science/data/replay_runtime}"

if [[ ! -d "$RUNTIME_DIR/incoming/transactions" ]]; then
    echo "No existen transacciones liberadas en: $RUNTIME_DIR/incoming" >&2
    echo "Ejecuta primero: ./mlops/scripts/run-replay.sh --next" >&2
    exit 3
fi

mkdir -p "$RUNTIME_DIR/features"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$RUNTIME_DIR:/app/data-science/data" \
    "$IMAGE_NAME" \
    --source incoming
