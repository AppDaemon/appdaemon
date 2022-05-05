#!/bin/sh

CONF=/conf
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

# if ENV HA_KEY is set, change the value in appdaemon.yaml
if [ -n "$TOKEN" ]; then
  sed -i "s/^      token:.*/      token: $(echo $TOKEN | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV CERT_VERIFY is set, change the value in appdaemon.yaml
if [ -n "$CERT_VERIFY" ]; then
  sed -i "s/^      cert_verify:.*/      cert_verify: $(echo $CERT_VERIFY | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
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

#install user-specific packages
apk add --no-cache $(find $CONF -name system_packages.txt | xargs cat | tr '\n' ' ')
#check recursively under CONF for additional python dependencies defined in requirements.txt
find $CONF -name requirements.txt -exec pip3 install --upgrade -r {} \;

# Lets run it!
exec appdaemon -c $CONF "$@"
