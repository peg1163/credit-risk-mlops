#!/usr/bin/env bash
# Fails when pushing one more release image would let the ECR lifecycle policy
# expire the image the endpoint is running (ADR-0005, ADR-0009).
#
# Usage: check-serving-rollback-window.sh <repository> <endpoint-name> [images-to-keep]

set -euo pipefail

REPOSITORY="$1"
ENDPOINT_NAME="$2"
KEEP="${3:-10}"

if ! CONFIG_NAME="$(aws sagemaker describe-endpoint --endpoint-name "$ENDPOINT_NAME" --query EndpointConfigName --output text 2>/dev/null)"; then
    echo "Endpoint $ENDPOINT_NAME does not exist; nothing to protect."
    exit 0
fi

MODEL_NAME="$(aws sagemaker describe-endpoint-config --endpoint-config-name "$CONFIG_NAME" --query 'ProductionVariants[0].ModelName' --output text)"
IMAGE="$(aws sagemaker describe-model --model-name "$MODEL_NAME" --query PrimaryContainer.Image --output text)"
DEPLOYED_DIGEST="${IMAGE##*@}"

if [[ "$DEPLOYED_DIGEST" != sha256:* ]]; then
    echo "The endpoint image is not referenced by digest: $IMAGE" >&2
    exit 1
fi

# Release images, newest first, as the lifecycle policy counts them.
RELEASES="$(aws ecr describe-images --repository-name "$REPOSITORY" --filter tagStatus=TAGGED --output json \
    | jq -r '[.imageDetails[] | select(any(.imageTags[]; startswith("v")))] | sort_by(.imagePushedAt) | reverse | .[].imageDigest')"

POSITION="$(grep -nxF "$DEPLOYED_DIGEST" <<<"$RELEASES" | cut -d: -f1 || true)"

if [[ -z "$POSITION" ]]; then
    echo "The deployed image $DEPLOYED_DIGEST is not a release (v*) image." >&2
    echo "Images tagged dev-* expire after 7 days; promote a release image before relying on the endpoint." >&2
    exit 1
fi

# After the push, the deployed image moves one position down.
if (( POSITION + 1 > KEEP )); then
    echo "The deployed image is release number $POSITION; one more push would expire it (keep=$KEEP)." >&2
    echo "Promote a newer release or raise serving_release_images_to_keep before pushing." >&2
    exit 1
fi

echo "Deployed image $DEPLOYED_DIGEST is release number $POSITION of $KEEP kept; the push is safe."
