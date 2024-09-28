#!/bin/bash

readonly REPO_DIR=$(cd $(dirname $(dirname $(readlink -f "${BASH_SOURCE[0]}"))) && pwd)

rm -rf ./build ./dist

if command -v uv >/dev/null 2>&1; then
    uv sync -U --all-extras
    uv build --wheel --refresh
else
    # uv is not installed
    echo "uv command not found. See https://docs.astral.sh/uv/getting-started/installation/"
    python -m build
fi

docker build -t acockburn/appdaemon:${1:-"local-dev"} .
