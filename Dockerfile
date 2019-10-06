FROM python:3.7-alpine

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

# Copy appdaemon into image
WORKDIR /usr/src/app
COPY . .

# Install timezone data
RUN apk add tzdata

# Fix for current dev branch
RUN pip3 install --no-cache-dir python-dateutil

# Install dependencies
RUN apk add --no-cache gcc libffi-dev musl-dev \
    && pip3 install --no-cache-dir .

# Install additional packages
RUN apk add --no-cache curl

# Start script
RUN chmod +x /usr/src/app/dockerStart.sh
ENTRYPOINT ["./dockerStart.sh"]
