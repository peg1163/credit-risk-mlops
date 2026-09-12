#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-credit-risk-replay:0.1.0}"
ARCHIVE_DIR="${ARCHIVE_DIR:-$PROJECT_ROOT/data-science/data/raw_archive}"
RUNTIME_DIR="${RUNTIME_DIR:-$PROJECT_ROOT/data-science/data/replay_runtime}"

if [[ $# -eq 0 ]]; then
    echo "Uso: $0 --status | --next | --release-month YYYY-MM | --reset" >&2
    exit 2
fi

if [[ ! -f "$ARCHIVE_DIR/dataset_manifest.json" ]]; then
    echo "No existe el archivo histórico esperado: $ARCHIVE_DIR" >&2
    exit 3
fi

mkdir -p "$RUNTIME_DIR"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$RUNTIME_DIR:/app/data-science/data" \
    --volume "$ARCHIVE_DIR:/app/data-science/data/raw_archive:ro" \
    "$IMAGE_NAME" \
    "$@"
