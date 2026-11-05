# When changing the base image tag, make sure that the python major and minor version matches that provided by alpine's
# python3 package (see https://pkgs.alpinelinux.org/packages), otherwise alpine py3-* packages won't work
# Due to incorrect PYTHONPATH. Keep PYTHON_RELEASE in step with the tag.
# Test from docker shell:
# $> apk add py3-scikit-learn
# $> python3
# >>> import sklearn
# (No error and it worked!)
# The image is written out literally (not via ARGs) so Dependabot can keep its digest up to date; Dependabot only
# refreshes the digest of this tag, moving to a new Python or Alpine version is a manual change.
ARG PYTHON_RELEASE=3.12
FROM python:3.12-alpine3.23@sha256:a4ad86fc2eaa4f9a5c3153776c9fb56e502dbd8e23dfa855d164308f376a6dd2 AS base

# Image for building dependencies (on architectures that don't provide a ready-made Python wheel)
FROM base AS builder

# Build arguments populated automatically by docker during build with the target architecture we are building for (eg: 'amd64')
# Useful to differentiate the build process for each architecture
# https://docs.docker.com/engine/reference/builder/#automatic-platform-args-in-the-global-scope
ARG TARGETARCH
ARG TARGETVARIANT
ARG PYTHON_RELEASE

ENV UV_LOCKED=true
ENV UV_COMPILE_BYTECODE=true
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_SYSTEM_PYTHON=true
ENV UV_NO_MANAGED_PYTHON=true
ENV PYTHONPATH="/usr/lib/python${PYTHON_RELEASE}/site-packages"

RUN --mount=type=cache,id=apk-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/var/cache/apk/ \
    apk add uv

ENV PATH="/root/.local/bin/:$PATH"

# A workaround for compiling the `orsjson` package with rust: see https://github.com/rust-lang/cargo/issues/6513#issuecomment-1440029221
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true

# If on ARM architecture install system packages to build native dependencies:
# - git and rust: build the `orsjson` package (required by `deepdiff`)
# - cython and build-base: build the `uvloop` package (build-base contains the set of basic tools to compile with gcc)
# - linux-headers: the libuv bundled with `uvloop` needs the kernel headers (e.g. `linux/errqueue.h`)
# Install system dependencies, saving the apk cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# Specify the architecture in the cache id, otherwise the apk cache of different architectures will conflict
RUN --mount=type=cache,id=apk-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/var/cache/apk/ \
    if [ "$TARGETARCH" = "arm" ]; then apk add git build-base cython linux-headers rust cargo; fi

# Install the Python dependencies of AppDaemon
# Save the pip cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# (specify the architecture in the cache id, otherwise the pip cache of different architectures will conflict)
RUN --mount=type=cache,id=uv-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --inexact --no-install-project --no-dev --no-editable

RUN --mount=type=cache,id=uv-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/root/.cache/uv \
    --mount=type=bind,source=./dist,target=/dist \
    uv pip install /dist/*.whl

ENTRYPOINT [ "/bin/ash" ]

###################################
# Runtime image
FROM base

ARG TARGETARCH
ARG TARGETVARIANT
ARG PYTHON_RELEASE

# Install curl to allow for healthchecks
RUN apk --no-cache add curl

# Copy sample configuration directory and entrypoint script
COPY ./conf /opt/conf
COPY ./scripts/start.sh /start.sh

# Copy the python dependencies built and installed in the previous stage
COPY --from=builder /usr/local /usr/local

ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_SYSTEM_PYTHON=true
ENV UV_NO_MANAGED_PYTHON=true
ENV PYTHONPATH="/usr/lib/python${PYTHON_RELEASE}/site-packages"

# API Port
EXPOSE 5050

# Mountpoints for configuration & certificates
VOLUME /conf
VOLUME /certs

WORKDIR /conf
ENTRYPOINT [ "/start.sh" ]

RUN --mount=type=cache,id=apk-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/var/cache/apk/ \
    apk add uv
