ARG IMAGE=python:3.9-alpine
FROM ${IMAGE}

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
RUN --mount=type=cache,target=/var/cache/apk/ \
    apk add tzdata build-base gcc libffi-dev openssl-dev musl-dev cargo rust curl

# Copy AppDaemon Python package into the image
WORKDIR /usr/src/app
COPY ./dist/*.whl .

# Install the Python package, saving the pip cache with docker mount: https://docs.docker.com/build/cache/#keep-layers-small
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install *.whl &&\
    rm *.whl

# Copy sample configuration directory and entrypoint script
COPY ./conf ./conf
COPY ./dockerStart.sh .

# Define entrypoint script
ENTRYPOINT ["./dockerStart.sh"]
