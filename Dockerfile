FROM python:3.4

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app
VOLUME /conf

RUN pip3 install --no-cache-dir \
  astral \
  configparser \
  daemonize \
  sseclient

# TODO
# COPY requirements.txt requirements.txt
# RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

CMD [ "/usr/local/bin/python", "/usr/src/app/bin/appdaemon.py", "/conf/appdaemon.cfg" ]
