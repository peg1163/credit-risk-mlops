#!/usr/bin/env bash
# Builds and pushes a test build of the serving image as dev-<sha7> (ADR-0009).
# Releases (v<semver>-<sha7>) are pushed only by the publish workflow from main.
#
# Usage: AWS_PROFILE=<profile> mlops/scripts/push-serving-image-dev.sh <repository-url>

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPOSITORY_URL="$1"
REGISTRY="${REPOSITORY_URL%%/*}"
REGION="$(cut -d. -f4 <<<"$REGISTRY")"
VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/mlops/docker/sagemaker-inference.version")"
SHA="$(git -C "$PROJECT_ROOT" rev-parse --short=7 HEAD)"
TAG="dev-$SHA"

# Tags are immutable: a build with uncommitted changes gets its own tag.
if [[ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]]; then
    TAG="$TAG-$(date -u +%Y%m%d%H%M%S)"
fi

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build \
    --file "$PROJECT_ROOT/mlops/docker/sagemaker-inference.Dockerfile" \
    --build-arg "IMAGE_VERSION=$VERSION-$TAG" \
    --tag "$REPOSITORY_URL:$TAG" \
    "$PROJECT_ROOT"
docker push "$REPOSITORY_URL:$TAG"

DIGEST="$(aws ecr describe-images --region "$REGION" --repository-name "${REPOSITORY_URL#*/}" --image-ids "imageTag=$TAG" --query 'imageDetails[0].imageDigest' --output text)"
echo "tag=$TAG"
echo "digest=$DIGEST"
echo "This image expires 7 days after the push; do not leave the endpoint on it."
