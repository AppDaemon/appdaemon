#!/bin/sh

# Default configuration directory used at runtime
CONF=/conf
# Directory containing sample config files to copy from
CONF_SRC=/usr/src/app/conf

# if configuration file doesn't exist, copy the default
if [ ! -f $CONF/appdaemon.yaml ]; then
  cp $CONF_SRC/appdaemon.yaml.example $CONF/appdaemon.yaml
fi

# if apps folder doesn't exist, copy the default
if [ ! -d $CONF/apps ]; then
  cp -r $CONF_SRC/apps $CONF/apps
fi

# if apps file doesn't exist, copy the default
if [ ! -f $CONF/apps/apps.yaml ]; then
  cp $CONF_SRC/apps/apps.yaml.example $CONF/apps/apps.yaml
fi

# if dashboards folder doesn't exist, copy the default
if [ ! -d $CONF/dashboards ]; then
  cp -r $CONF_SRC/dashboards $CONF/dashboards
fi

# if ENV HA_URL is set, change the value in appdaemon.yaml
if [ -n "$HA_URL" ]; then
  sed -i "s/^      ha_url:.*/      ha_url: $(echo $HA_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV TOKEN is set, change the value in appdaemon.yaml
if [ -n "$TOKEN" ]; then
  sed -i "s/^      token:.*/      token: $(echo $TOKEN | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# MQTT plugin
if [[ -n "$MQTT_NAMESPACE" && -n "$MQTT_CLIENT_HOST" && -n "$MQTT_CLIENT_USER" && -n "$MQTT_CLIENT_PASSWORD" ]]; then
  # Plugin skeleton
  sed -i "s/^http:.*/    MQTT:\n      type: mqtt\n      namespace:\n      client_host:\n      client_user:\n      client_password:\nhttp:/" $CONF/appdaemon.yaml

  # Plugin variables
  sed -i "s/^      namespace:.*/      namespace: $(echo $MQTT_NAMESPACE | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
  sed -i "s/^      client_host:.*/      client_host: $(echo $MQTT_CLIENT_HOST | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
  sed -i "s/^      client_user:.*/      client_user: $(echo $MQTT_CLIENT_USER | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
  sed -i "s/^      client_password:.*/      client_password: $(echo $MQTT_CLIENT_PASSWORD | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV HA_CERT_VERIFY is set, change the value in appdaemon.yaml
if [ -n "$HA_CERT_VERIFY" ]; then
  sed -i "s/^      cert_verify:.*/      cert_verify: $(echo $HA_CERT_VERIFY | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV DASH_URL is set, change the value in appdaemon.yaml
if [ -n "$DASH_URL" ]; then
  if grep -q "^  url" $CONF/appdaemon.yaml; then
    sed -i "s/^  url:.*/  url: $(echo $DASH_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
  else
    sed -i "s/# Apps/HADashboard:\r\n  url: $(echo $DASH_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')\r\n# Apps/" $CONF/appdaemon.yaml
  fi
fi

# if ENV TIMEZONE is set, change the value in appdaemon.yaml
if [ -n "$TIMEZONE" ]; then
  sed -i "s/^  time_zone:.*/  time_zone: $(echo $TIMEZONE | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV LATITUDE is set, change the value in appdaemon.yaml
if [ -n "$LATITUDE" ]; then
  sed -i "s/^  latitude:.*/  latitude: $LATITUDE/" $CONF/appdaemon.yaml
fi

# if ENV LONGITUDE is set, change the value in appdaemon.yaml
if [ -n "$LONGITUDE" ]; then
  sed -i "s/^  longitude:.*/  longitude: $LONGITUDE/" $CONF/appdaemon.yaml
fi

# if ENV ELEVATION is set, change the value in appdaemon.yaml
if [ -n "$ELEVATION" ]; then
  sed -i "s/^  elevation:.*/  elevation: $ELEVATION/" $CONF/appdaemon.yaml
fi

# Install packages specified by the end-user.
# - Recusively traverse $CONF directory, searching for non-empty system_packages.txt files
# - Use cat to read all the file contents, use echo to append whtespace " " char to the file content (to guard against the corner case where the user does not put a newline after the package name)
# - Use tr to substitute all newlines with " " char, to concatenate the name of all packages in a single line
# - Pipe to xargs, printing the executed command (-t), invoking `apk add` with the list of required packages. Do nothing if no system_packages.txt files is present (--no-run-if-empty)
find $CONF -name system_packages.txt -type f -not -empty -exec cat {} \; -exec echo -n " " \; | tr '\n' ' ' | xargs -t --no-run-if-empty apk add

# Check recursively under $CONF directory for additional python dependencies defined by the end-user via requirements.txt
find $CONF -name requirements.txt -type f -not -empty -exec pip3 install --upgrade -r {} \;

# Lets run it!
exec python3 -m appdaemon -c $CONF "$@"
