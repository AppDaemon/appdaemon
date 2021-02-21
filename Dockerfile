FROM python:3.8-slim

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

# Install dependencies
ADD ./requirements.txt ./requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

# Add appdaemon to image
ADD . .
RUN pip install --no-cache-dir .

# Start script
RUN chmod +x /usr/src/app/dockerStart.sh
ENTRYPOINT ["./dockerStart.sh"]
