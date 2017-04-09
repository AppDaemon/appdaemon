# Appdaemon with Docker
A quick tutorial to Appdaemon with Docker

## About Docker
Docker is a popular application container technology. Simply put, the technology allows an application to be built in a known-state and run in its own isolated world, totally independant of other applications. This allows you to run different applications that may have conflicting requirements on the same system, as well as making applications extremely portable and very easy to get up and running. It also allows you to run multiple versions or copies of the same application at the same time! And no messy cleanups required. Containers are powerful, however they require abstractions that can sometimes be confusing. 

This guide will help you get Appdaemon running under Docker and hopefully help you become more comfortable with using Docker. There are multiple and fancier ways of doing some of these steps which are removed for the sake of keeping it simple. As your needs change, just remember there's probably a way to do what you want :)

## Prereqs
This guide assumes:
* You already have Docker installed on the system you want to run Appdaemon on. If you still need to do this, follow the [Docker Installation documentation](https://docs.docker.com/engine/installation/)
* You have Home Assistant up and running
* You are comfortable with some tinkering. This is a pre-req for Appdaemon too!

## Testing your System
Our first step will be to verify that we can get Appdaemon running on our machine, which tests that we can successfully "pull" (download) software from Docker Hub, execute it, and get output that Appdaemon is working. We will worry about our persistent (normal) configuration later.

Before you start, you need to know the following:
* HA_URL: The URL of your running Home Assistant, in the form of http://[name]:[port]. Port is probably 8123. 
* HA_KEY: If your Home Assistant requires an API key, you'll need that

Now, on your Docker host, run the following command, substituting the values above in the quotes below. (Note, if you do not need an HA_KEY, you can omit the entire -e HA_KEY line)
```
docker run --rm -it -p 5050:5050 \
  -e HA_URL="<your HA_URL value>" \
  -e HA_KEY="<your HA_KEY value>" \
  -e DASH_URL="http://$HOSTNAME:5050" \
  quadportnick/appdaemon:latest
```
You should see some download activity the first time you run this as it downloads the latest Appdaemon image. After that is downloaded, Docker will create a container based on that image and run. It will automatically delete itself when it exits, since right now we are just testing.

You will see Appdaemon's output appear on your screen, and you should look for lines like these being output:

Appdaemon successfully connected to Home Assistant
```
2017-04-01 14:26:48.361140 INFO Connected to Home Assistant 0.40.0
```

The 'apps' capability of Appdaemon is working, running the example Hello World app
```
2017-04-01 14:26:48.330084 INFO hello_world: Hello from AppDaemon
2017-04-01 14:26:48.333040 INFO hello_world: You are now ready to run Apps!
```

The 'dashboard' capability of Appdaemon has started. 
```
2017-04-01 14:26:48.348260 INFO HADashboard Started
2017-04-01 14:26:48.349135 INFO Listening on ('0.0.0.0', 5050)
```
Now open up a web browser, and browse to http://docker_host_name:5050. You should see the "Welcome to HADashboard for Home Assistant" screen and see the Hello dashboard is available.

If all of these checks work, congratulations! Docker and Appdaemon are working great on your system! Hit Control-C to cause Appdaemon to shutdown, and Docker will clean up and return to the command line. It's almost as if nothing happened... :)


## Persistent Configuration
Since Docker containers are considered ephimeral, any state that you want to be able to preserve must be stored outside of the container. In the case of Appdaemon, you would be concerned about your `conf` folder.

The first step is to create a location on your filesystem to store the `conf` folder. It does not matter where this is, some people like to store it in the same location as Home Assistant. The main concern would be if you are going to run multiple copies of Appdaemon, you will want to have different `conf` folders for each instance to avoid write conflicts. This isn't a problem for most people, however it is something to keep in mind.

I like to keep a folder structure under `/docker` on my systems, so we can simply do something like:
```
mkdir -p /docker/appdaemon/conf
```

Next, we will run a container again, omiting the `--rm -it` parameters so that it stays background and doesn't disappear when it exits. We will also add `--restart=always` so that the container will auto-start and restart on failures, and lastly specify our `conf` folder location.

```
docker run --restart always -p 5050:5050 \
  --name appdaemon \
  -e HA_URL="<your HA_URL value>" \
  -e HA_KEY="<your HA_KEY value>" \
  -e DASH_URL="http://$HOSTNAME:5050" \
  -v <your conf folder>:/conf \ 
  quadportnick/appdaemon:latest
```

I would suggest documenting the command line above in your notes, so that you have it as a reference in the future for rebuilding and upgrading. If you back up your command line, as well as your `conf` folder, you can trivially restore Appdaemon on another machine or on a rebuild.

If your `conf` folder is brand new, the Appdaemon Docker will copy the default configuration files into this folder. If there are already configuration files, it will not overwrite them. Double check that the files are there now

```
ls /docker/appdaemon/conf
```

Appdaemon is ready! You can edit the configuration files in this folder and Appdaemon will dynamically reload as appropriate :) The application will automatically start when your system reboots via Docker.

## Upgrading Appdaemon
Upgrading under Docker really doesn't exist. As stated before, containers are considered ephimeral. Therefore, the process of upgrading is removing the container running the old version, and starting up a container with the new version. Since the the persistent state (`conf`) was kept, it is effectively an upgrade.

Run the following commands:
```
docker stop appdaemon
docker rm appdaemon
docker pull quadportnick/appdaemon:latest
docker run --restart always -p 5050:5050 \
  --name appdaemon \
  -e HA_URL="<your HA_URL value>" \
  -e HA_KEY="<your HA_KEY value>" \
  -e DASH_URL="http://$HOSTNAME:5050" \
  -v <your conf folder>:/conf \ 
  quadportnick/appdaemon:latest
```

## Controlling the Appdaemon Conter
To restart Appdaemon:
```
docker restart appdaemon
```

To stop Appdaemon:
```
docker stop appdaemon
```

To start Appdaemon back up after stopping:
```
docker start appdaemon
```

To check the running state, run the following and look at this 'STATUS' column:
```
docker ps -a
```


## Viewing Log Output
You can view the output of your Appdaemon with this command:
```
docker logs appdaemon
```


## Running with Appdaemon Debug
Run the following commands to run debug with the existing container temporarily:
```
docker stop appdaemon
docker exec -i appdaemon /bin/bash -c "export EXTRA_CMD='-D DEBUG' && ./dockerStart.sh"
```

After you have debugged, start the container back up as normal
```
docker start appdaemon
```

If you need to have a persistent debug state, recreate the container from scratch with `-e EXTRA_CMD="-D DEBUG"` to the `docker run` command line

## Home Assistant SSL
If your Home Assistant is running with self-signed certificates, you will want to point to the location of the certificate files as part of the container creation process. Add `-v <your cert path>:/certs` to the `docker run` command line
