#!/usr/bin/env bash

# Multi-platform Docker Build and Size Analysis Script
# This script builds Docker images for multiple platforms and analyzes their sizes

set -e  # Exit on any error

readonly REPO_DIR=$(cd $(dirname $(dirname $(readlink -f "${BASH_SOURCE[0]}"))) && pwd)

# Configuration
PLATFORMS="linux/arm64/v8,linux/amd64,linux/arm/v7,linux/arm/v6"
# PLATFORMS="linux/arm64/v8,linux/amd64"
IMAGE_TAG="acockburn/appdaemon:local-dev"
BUILD_DIR="${REPO_DIR}/build"
DOCKER_BUILD_DIR="${BUILD_DIR}/docker"
DOCKERFILE="${REPO_DIR}/Dockerfile"
ARCHIVE_NAME="appdaemon-docker.tar"
ARCHIVE_PATH="${DOCKER_BUILD_DIR}/${ARCHIVE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
print_status "Checking prerequisites..."

if ! command_exists docker; then
    print_error "Docker is not installed or not in PATH"
    exit 1
fi

if ! command_exists jq; then
    print_error "jq is not installed. Please install jq to parse JSON output."
    exit 1
fi

# Check if docker buildx is available
if ! docker buildx version >/dev/null 2>&1; then
    print_error "Docker buildx is not available. Please ensure you have Docker Desktop or a recent Docker version."
    exit 1
fi

print_success "All prerequisites are available"

print_status "Cleaning build directories..."
rm -rf "${BUILD_DIR}" "${REPO_DIR}/dist"

# Build the Python package first (equivalent to Build Package task)
print_status "Building Python package..."
if command_exists uv; then
    uv build --wheel --refresh -q
else
    print_error "uv is not installed. Please install uv or build the package manually."
    exit 1
fi

print_success "Python package built"

# Setup buildx builder
print_status "Setting up Docker buildx builder..."

BUILDER_NAME="multiplatform"

# Check if builder already exists
if docker buildx ls | grep -q "$BUILDER_NAME"; then
    print_warning "Builder '$BUILDER_NAME' already exists, using existing builder"
else
    print_status "Creating new builder instance..."
    docker buildx create --name "$BUILDER_NAME" --driver docker-container --use
fi

# Use the builder
docker buildx use "$BUILDER_NAME"

# Bootstrap the builder
print_status "Bootstrapping builder (this may take a moment)..."
docker buildx inspect --bootstrap

print_success "Builder setup complete"

# Create build directory
print_status "Creating docker build output directory..."
mkdir -p "${DOCKER_BUILD_DIR}"

# Build multi-platform images and export to OCI archive
print_status "Building multi-platform Docker images..."
print_status "Platforms: $PLATFORMS"
print_status "This may take several minutes..."

docker buildx build \
    --pull \
    --platform "$PLATFORMS" \
    --tag "$IMAGE_TAG" \
    --output "type=oci,dest=${ARCHIVE_PATH}" \
    -f ${DOCKERFILE} \
    ${REPO_DIR}

print_success "Multi-platform images built and exported"

# Extract the archive
print_status "Extracting OCI archive..."
cd "$DOCKER_BUILD_DIR"
tar -xf "$ARCHIVE_NAME"

print_success "Archive extracted"

# Parse the index.json to get the multi-platform manifest digest
print_status "Analyzing image manifests..."

MAIN_MANIFEST_DIGEST=$(jq -r '.manifests[0].digest' index.json | cut -d: -f2)
MAIN_MANIFEST_FILE="blobs/sha256/$MAIN_MANIFEST_DIGEST"

if [ ! -f "$MAIN_MANIFEST_FILE" ]; then
    print_error "Main manifest file not found: $MAIN_MANIFEST_FILE"
    exit 1
fi

# Get platform-specific manifests
PLATFORM_MANIFESTS=$(jq -r '.manifests[] | select(.platform.architecture != "unknown") | "\(.platform.os)/\(.platform.architecture)\(.platform.variant // "") \(.digest)"' "$MAIN_MANIFEST_FILE")

print_success "Found platform manifests"

# Initialize totals
TOTAL_SIZE=0
PLATFORM_COUNT=0

echo
echo "========================================"
echo "Multi-Platform Docker Image Size Report"
echo "========================================"
echo
printf "%-20s %15s\n" "Platform" "Compressed Size"
printf "%-20s %15s\n" "--------" "---------------"

# Loop through each platform manifest
while IFS=' ' read -r platform digest; do
    if [ -z "$platform" ] || [ -z "$digest" ]; then
        continue
    fi

    MANIFEST_HASH=$(echo "$digest" | cut -d: -f2)
    MANIFEST_FILE="blobs/sha256/$MANIFEST_HASH"

    if [ ! -f "$MANIFEST_FILE" ]; then
        print_warning "Manifest file not found for $platform: $MANIFEST_FILE"
        continue
    fi

    # Calculate total size of all layers for this platform
    PLATFORM_SIZE=$(jq -r '.layers[].size' "$MANIFEST_FILE" | awk '{sum += $1} END {print sum}')

    # Convert to MB (using awk instead of bc for better compatibility)
    PLATFORM_SIZE_MB=$(echo "$PLATFORM_SIZE" | awk '{printf "%.2f", $1/1024/1024}')

    printf "%-20s %12s MB\n" "$platform" "$PLATFORM_SIZE_MB"

    TOTAL_SIZE=$((TOTAL_SIZE + PLATFORM_SIZE))
    PLATFORM_COUNT=$((PLATFORM_COUNT + 1))

done <<< "$PLATFORM_MANIFESTS"

# Calculate average
if [ $PLATFORM_COUNT -gt 0 ]; then
    AVERAGE_SIZE_MB=$(echo "$TOTAL_SIZE $PLATFORM_COUNT" | awk '{printf "%.2f", $1/$2/1024/1024}')
    ARCHIVE_SIZE_MB=$(du -m "$ARCHIVE_NAME" | cut -f1)

    echo
    echo "Summary:"
    echo "--------"
    printf "Total platforms:     %d\n" "$PLATFORM_COUNT"
    printf "Average image size:  %s MB\n" "$AVERAGE_SIZE_MB"
    printf "Archive size:        %d MB (includes all platforms + metadata)\n" "$ARCHIVE_SIZE_MB"
fi

echo
print_success "Analysis complete!"
print_status "Build artifacts are in: $DOCKER_BUILD_DIR"

# Return to original directory
cd - > /dev/null
