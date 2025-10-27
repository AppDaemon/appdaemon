.PHONY: test wheel dev-container multiplatform-dev-container dev-docs

test:
	uv run pytest

wheel:
	uv build --wheel --refresh

dev-container:
	./scripts/docker-build.sh

multiplatform-dev-container:
	./scripts/multiplatform-docker-build.sh

dev-docs:
	uv run \
    --extra doc \
    sphinx-autobuild \
    --show-traceback --fresh-env \
    --host 0.0.0.0 --port 9999 \
    --watch ./appdaemon \
    --watch ./tests \
    docs/ build/docs
