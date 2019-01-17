FROM python:3.6

# Environment vars we can configure against
# But these are optional, so we won't define them now
#ENV HA_URL http://hass:8123
#ENV HA_KEY secret_key
#ENV DASH_URL http://hass:5050
#ENV EXTRA_CMD -D DEBUG

# Port for dashboards
EXPOSE 5050

# Mountpoints for user config and certificates
VOLUME /conf
VOLUME /certs

# Copy AppDaemon into image
WORKDIR /usr/src/app
COPY . .

# Install
RUN pip3 install . && \
    chmod +x dockerStart.sh && \
    rm -rf /tmp/* ~/.cache

# Start script
ENTRYPOINT ["./dockerStart.sh"]
