ARG IMAGE=alpine:3.15
FROM ${IMAGE} as builder

WORKDIR /build

# Install dependencies
RUN apk add --no-cache git python3 python3-dev py3-pip py3-wheel build-base gcc libffi-dev openssl-dev musl-dev cargo

# Fetch requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM ${IMAGE}

# Environment vars we can configure against
# But these are optional, so we won't define them now
#ENV HA_URL http://hass:8123
#ENV HA_KEY secret_key
#ENV DASH_URL http://hass:5050
#ENV EXTRA_CMD -D DEBUG

# API Port
EXPOSE 5050

# Mountpoints for configuration & certificates
VOLUME /conf
VOLUME /certs

WORKDIR /usr/src/app

# Install runtime required packages
# First line is required, 2nd line is for backwards compatibility
RUN apk add --no-cache curl python3 py3-pip tzdata \
        git py3-wheel build-base gcc libffi-dev openssl-dev musl-dev cargo

# Copy compiled deps from builder image
COPY --from=builder /usr/lib/python3.9/site-packages/ /usr/lib/python3.9/site-packages/

# Copy appdaemon into image
COPY . .

# Start script
RUN chmod +x /usr/src/app/dockerStart.sh
ENTRYPOINT ["./dockerStart.sh"]
