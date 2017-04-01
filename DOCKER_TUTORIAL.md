# Appdaemon with Docker
A quick guide to Appdaemon with Docker

## About Docker
Docker is a popular application container technology. Simply put, the technology allows an application to be built in a known-state and run in its own isolated world, totally independant of other applications. This allows you to run different applications that may have conflicting requirements on the same system, as well as making applications extremely portable and very easy to get up and running. It also allows you to run multiple versions or copies of the same application at the same time! 

Containers are powerful, however they require abstractions that can sometimes be confusing. This guide will help you get Appdaemon running, understanding there's even fancier ways to do some of these steps that are best left for the Docker ninjas.

## Prereqs
This guide assumes:
* You already have Docker installed on the system you want to run Appdaemon on
* If you are using Docker for Windows, that it is set to Linux containers mode
* You are comfortable with some tinkering. This is a pre-req for Appdaemon too :)

## Getting Started
Our first step will be to verify that we can get Appdaemon running on our machine, which tests that we can successfully "pull" (download) software from Docker Hub, execute it, and get output that Appdaemon is working. We will worry about our perminent configuration later.

Before you start, you need to know the following:
* HA_URL: The URL of your running Home Assistant, in the form of http://[name]:[port]. Port is probably 8123. 
* HA_KEY: If your Home Assistant requires an API key, you'll need that

Now, on your Docker host, run the following command, substituting the values above in the quotes below. If you do not have an HA_KEY, you can omit the -e HA_KEY piece.
```
docker run --rm -it -p 5050:5050 -e HA_URL="<your HA_URL value>" -e HA_KEY="<your HA_KEY value>" -e DASH_URL="http://$HOSTNAME:5050" quadportnick/appdaemon:latest
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

If all of these checks work, congratulations! Docker and Appdaemon are a go on your system!

## Permanent Configuration

