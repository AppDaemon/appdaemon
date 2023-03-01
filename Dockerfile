ARG IMAGE=python:3.10-alpine
FROM ${IMAGE}

# Build arguments populated automatically by docker during build with the target architecture we are building for (eg: 'amd64')
# Usefuil to differentiate the build process for each architecture
# https://docs.docker.com/engine/reference/builder/#automatic-platform-args-in-the-global-scope
ARG TARGETARCH
ARG TARGETVARIANT

# Environment vars we can configure against
# But these are optional, so we won't define them now
#ENV HA_URL http://hass:8123
#ENV HA_KEY secret_key
#ENV DASH_URL http://hass:5050

# API Port
EXPOSE 5050

# Mountpoints for configuration & certificates
VOLUME /conf
VOLUME /certs

# Install system dependencies, saving the apk cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# Specify the architecture in the cache id, otherwise the apk cache of different architectures will conflict
RUN --mount=type=cache,id=apk-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/var/cache/apk/ \
    apk add tzdata build-base gcc libffi-dev openssl-dev musl-dev cargo rust curl

WORKDIR /usr/src/app

# Install the Python package, saving the pip cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# Specify the architecture in the cache id, otherwise the pip cache of different architectures will conflict
RUN --mount=type=cache,id=pip-${TARGETARCH}-${TARGETVARIANT},sharing=locked,target=/root/.cache/pip \
    # Mount the project directory containing the built Python package in the image, so it is available for pip install
    --mount=type=bind,source=./dist/,target=/usr/src/app/ \
    # Install the package
    pip install *.whl

# Copy sample configuration directory and entrypoint script
COPY ./conf ./conf
COPY ./dockerStart.sh .


# Define entrypoint script
ENTRYPOINT ["./dockerStart.sh"]
