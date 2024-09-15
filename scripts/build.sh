#!/bin/bash

readonly REPO_DIR=$(cd $(dirname $(dirname $(readlink -f "${BASH_SOURCE[0]}"))) && pwd)

rm -rf ./build ./dist

git pull

if command -v rye >/dev/null 2>&1; then
    RYE_INSTALLED=true
    rye sync
    rye build --wheel --clean
else
    RYE_INSTALLED=false
    python -m build
fi

docker build -t acockburn/appdaemon:${1:-"local-dev"} .
