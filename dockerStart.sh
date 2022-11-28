#!/bin/sh

CONF=/conf
CONF_SRC=/usr/src/app/conf

# if configuration file doesn't exist, copy the default
if [ ! -f $CONF/appdaemon.yaml ]; then
  cp $CONF_SRC/appdaemon.yaml.example $CONF/appdaemon.yaml
fi

# get app_dir from config, else use default
APPDIR=$(cat $CONF/appdaemon.yaml | sed -n 's/\s*app_dir:\s*\(.*\)$/\1/p')
case "${APPDIR}" in
  !env_var*) # add_dir pointing to env
    APPDIR_ENV=$(echo "$APPDIR" | sed -n 's/!env_var\s*\(.*\)/\1/p')
    echo "read app_dir from env ${APPDIR_ENV}"
    APPDIR=$(printenv "${APPDIR_ENV}")
    echo "app_dir set via env to: ${APPDIR}"
    ;;
  "") # set default if not configured.
    APPDIR="${CONF}/apps"
    echo "use default app_dir: ${APPDIR}"
    ;;
  *)
    echo "app_dir configured as ${APPDIR}"
esac

# if apps folder doesn't exist, copy the default
if [ ! -d "${APPDIR}" ]; then
  cp -r $CONF_SRC/apps "${APPDIR}"
  # if apps file doesn't exist, copy the default
  if [ ! -f "${APPDIR}/apps.yaml" ]; then
    cp $CONF_SRC/apps/apps.yaml.example "${APPDIR}/apps.yaml"
  fi
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

if [ $(id -u) = 0 ]; then
  #install user-specific packages if running as root
  apk add --no-cache $(find $CONF -name system_packages.txt | xargs cat | tr '\n' ' ')
  pip_param=""
else
  # install dependencies into user context instead of container wide
  pip_param="--user"
fi
#check recursively under CONF and APPDIR for additional python dependencies defined in requirements.txt
find $CONF -name requirements.txt -exec pip3 install $pip_param --upgrade -r {} \;
find $APPDIR -name requirements.txt -exec pip3 install $pip_param --upgrade -r {} \;

echo "Starting appdaemon with following config:"
cat $CONF/appdaemon.yaml
echo "################################"

# Lets run it!
exec appdaemon -c $CONF "$@"
