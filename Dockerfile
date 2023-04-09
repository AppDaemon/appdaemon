# When changing this, make sure that the python major and minor version matches that provided by alpine's python3
# package (see https://pkgs.alpinelinux.org/packages), otherwise alpine py3-* packages won't work
ARG PYTHON_RELEASE=3.10 ALPINE_VERSION=3.17
ARG BASE_IMAGE=python:${PYTHON_RELEASE}-alpine${ALPINE_VERSION}
# Image for building dependencies (on architectures that don't provide a ready-made Python wheel)
FROM ${BASE_IMAGE} as builder

# Build arguments populated automatically by docker during build with the target architecture we are building for (eg: 'amd64')
# Useful to differentiate the build process for each architecture
# https://docs.docker.com/engine/reference/builder/#automatic-platform-args-in-the-global-scope
ARG TARGETARCH
ARG TARGETVARIANT

# A workaround for compiling the `orsjson` package with rust: see https://github.com/rust-lang/cargo/issues/6513#issuecomment-1440029221
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true

# If on ARM architecture install system packages to build native dependencies:
# - git and rust: build the `orsjson` package (required by `deepdiff`)
# - cython and build-base: build the `uvloop` package (build-base contains the set of basic tools to compile with gcc)
# Install system dependencies, saving the apk cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# Specify the architecture in the cache id, otherwise the apk cache of different architectures will conflict
RUN --mount=type=cache,id=apk-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/var/cache/apk/ \
    if [ "$TARGETARCH" = "arm" ]; then\
        apk add git rust cargo &&\
        apk add build-base cython;\
    fi

# Copy requirements file of AppDaemon
COPY ./requirements.txt /usr/src/app/

# Install the Python dependencies of AppDaemon
# Save the pip cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# (specify the architecture in the cache id, otherwise the pip cache of different architectures will conflict)
RUN --mount=type=cache,id=pip-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/root/.cache/pip \
    pip install -r /usr/src/app/requirements.txt

###################################
# Runtime image
FROM ${BASE_IMAGE}

ARG TARGETARCH
ARG TARGETVARIANT
ARG PYTHON_RELEASE

# Copy the python dependencies built and installed in the previous stage
COPY --from=builder /usr/local/lib/python${PYTHON_RELEASE}/site-packages /usr/local/lib/python${PYTHON_RELEASE}/site-packages

WORKDIR /usr/src/app

# Install Appdaemon from the Python package built in the project `dist/` folder
RUN --mount=type=cache,id=pip-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/root/.cache/pip,from=builder \
    # Mount the project directory containing the built Python package, so it is available for pip install inside the container
    --mount=type=bind,source=./dist/,target=/usr/src/app/ \
    # Install the package
    pip install *.whl

# Copy sample configuration directory and entrypoint script
COPY ./conf ./conf
COPY ./dockerStart.sh .

# API Port
EXPOSE 5050

# Mountpoints for configuration & certificates
VOLUME /conf
VOLUME /certs

# Add paths used by alpine python packages to python search path
ENV PYTHONPATH=/usr/lib/python${PYTHON_RELEASE}:/usr/lib/python${PYTHON_RELEASE}/site-packages

# Define entrypoint script
ENTRYPOINT ["./dockerStart.sh"]

# Install curl to allow for healthchecks
RUN apk --no-cache add curl
