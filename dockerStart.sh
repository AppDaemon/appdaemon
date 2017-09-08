#!/bin/sh

CONF=/conf
CONF_SRC=/usr/src/app/conf

# if configuration file doesn't exist, copy the default
if [ ! -f $CONF/appdaemon.yaml ]; then
  cp $CONF_SRC/appdaemon.yaml.example $CONF/appdaemon.yaml
fi

# if apps file doesn't exist, copy the default
if [ ! -f $CONF/apps.yaml ]; then
  cp $CONF_SRC/apps.yaml.example $CONF/apps.yaml
fi

# if apps folder doesn't exist, copy the default
if [ ! -d $CONF/apps ]; then
  cp -r $CONF_SRC/apps $CONF/apps
fi

# if dashboards folder doesn't exist, copy the default
if [ ! -d $CONF/dashboards ]; then
  cp -r $CONF_SRC/dashboards $CONF/dashboards
fi

# if ENV HA_URL is set, change the value in appdaemon.yaml
if [ -n "$HA_URL" ]; then
  sed -i "s/^  ha_url:.*/  ha_url: $(echo $HA_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV HA_KEY is set, change the value in appdaemon.yaml
if [ -n "$HA_KEY" ]; then
  sed -i "s/^  ha_key:.*/  ha_key: $(echo $HA_KEY | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
fi

# if ENV DASH_URL is set, change the value in appdaemon.yaml
if [ -n "$DASH_URL" ]; then
  if grep -q "^  dash_url" $CONF/appdaemon.yaml; then
    sed -i "s/^  dash_url:.*/  dash_url: $(echo $DASH_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')/" $CONF/appdaemon.yaml
  else
    sed -i "s/# Apps/HADashboard:\r\n  dash_url: $(echo $DASH_URL | sed -e 's/\\/\\\\/g; s/\//\\\//g; s/&/\\\&/g')\r\n# Apps/" $CONF/appdaemon.yaml
  fi
fi

# Lets run it!
appdaemon -c $CONF $EXTRA_CMD