FROM python:3.4

#For Raspberry Pi use this instead
#FROM resin/raspberrypi-python:3.4

VOLUME /conf
VOLUME /certs
EXPOSE 5050

# Environment vars we can configure against
# But these are optional, so we won't define them now
#ENV HA_URL http://hass:8123
#ENV HA_KEY secret_key
#ENV DASH_URL http://hass:5050
#ENV EXTRA_CMD -D DEBUG

# Copy appdaemon into image
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
COPY . .

# Docker specific mods
RUN sed -i 's/loop.create_server(handler, conf.dash_host/loop.create_server(handler, "0.0.0.0"/g' /usr/src/app/appdaemon/appdash.py

# Install
RUN pip3 install .

# Start script
RUN chmod +x /usr/src/app/dockerStart.sh
CMD [ "./dockerStart.sh" ]
