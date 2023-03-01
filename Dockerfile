ARG IMAGE=alpine:3.17
FROM ${IMAGE} as builder

WORKDIR /build

# Install dependencies
RUN apk add --no-cache git python3 python3-dev py3-pip py3-wheel build-base gcc libffi-dev openssl-dev musl-dev cargo

# Fetch requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM ${IMAGE}

# Build argument populated automatically by docker during build with the target architecture we are building for (eg: 'amd64')
# Usefuil to differentiate the build process for each architecture
# https://docs.docker.com/engine/reference/builder/#automatic-platform-args-in-the-global-scope
ARG TARGETARCH

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
RUN --mount=type=cache,id=apk-${TARGETARCH},sharing=locked,target=/var/cache/apk/ \
    apk add tzdata build-base gcc libffi-dev openssl-dev musl-dev cargo rust curl

WORKDIR /usr/src/app

# Install the Python package, saving the pip cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
# Specify the architecture in the cache id, otherwise the pip cache of different architectures will conflict
RUN --mount=type=cache,id=pip-${TARGETARCH},sharing=locked,target=/root/.cache/pip \
    # Mount the project directory containing the built Python package in the image, so it is available for pip install
    --mount=type=bind,source=./dist/,target=/usr/src/app/ \
    # Install the package
    pip install *.whl

# Copy sample configuration directory and entrypoint script
COPY ./conf ./conf
COPY ./dockerStart.sh .


# Define entrypoint script
ENTRYPOINT ["./dockerStart.sh"]
