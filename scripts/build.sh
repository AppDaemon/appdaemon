#!/usr/bin/env bash

set -e

readonly REPO_DIR=$(cd $(dirname $(dirname $(readlink -f "${BASH_SOURCE[0]}"))) && pwd)

rm -rf ./build ./dist

if command -v uv >/dev/null 2>&1; then
    uv sync -U --all-extras
    echo -n "Building wheel..."
    uv build --wheel --refresh -q
    echo "done."
else
    # uv is not installed
    echo "uv command not found. See https://docs.astral.sh/uv/getting-started/installation/"
    python -m build
fi

docker build --pull -t acockburn/appdaemon:${1:-"local-dev"} .
