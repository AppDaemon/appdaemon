FROM python:3.4

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
VOLUME /conf

# Copy source
COPY . .

# INSTALL

RUN pip3 install .

CMD [ "appdaemon", "-c", "/conf"]