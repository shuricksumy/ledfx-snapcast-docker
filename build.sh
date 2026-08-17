#!/bin/bash
set -e

# Build Snapcast multiarch (arm64 and amd64) Docker images on macOS

IMAGE_NAME="snapcast"
PLATFORMS="linux/amd64,linux/arm64"
DOCKERFILE="Dockerfile"

# Check for Docker Buildx
if ! docker buildx version &>/dev/null; then
    echo "Docker Buildx is required. Please install Docker Desktop >= 2.2.2.0"
    exit 1
fi

# Create buildx builder if not exists
if ! docker buildx inspect multiarch-builder &>/dev/null; then
    docker buildx create --name multiarch-builder --use
fi

docker buildx use multiarch-builder

# Build multiarch image
# Snapcast .deb packages are fetched from the upstream GitHub release during
# the build; SNAPCAST_VERSION=latest resolves the newest one. Pin a tag
# (e.g. v0.35.0) here if you need a reproducible build.
docker buildx build \
    --platform $PLATFORMS \
    --build-arg SNAPCAST_VERSION="${SNAPCAST_VERSION:-latest}" \
    --build-arg REFRESH_WEEK="$(date -u +%G-W%V)" \
    -t $IMAGE_NAME:latest \
    -f $DOCKERFILE \
    --push .

echo "Multiarch image build and pushed: $IMAGE_NAME:latest"