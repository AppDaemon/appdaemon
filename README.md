# Description

AppDaemon is a loosely coupled, multi-threaded, sandboxed python
execution environment for writing automation apps for various types of Home Automation Software including [Home
Assistant](https://home-assistant.io/) and MQTT. It has a pluggable architecture allowing it to be integrated with
practically any event driven application.

It also provides a configurable dashboard (HADashboard)
suitable for wall mounted tablets.

# Release Cycle Frequency

AppDaemon has reached a very stable point, works reliably and is fairly feature rich at this point
in its development. For that reason, releases have been slow in recent months. This does not mean that AppDaemon has been abandoned -
 it is used every day by the core developers and has an active discord server [here](https://discord.gg/qN7c7JcFjk) - please join us for tips
and tricks, AppDaemon discussions and general home automation.

For full instructions on installation and use check out the [AppDaemon Project Documentation](http://appdaemon.readthedocs.io).

## Build image for multiple architectures

`$ make multiple`

## Development of the AppDaemon library

We use [pre-commit](https://pre-commit.com) for linting of the code, so `pip install pre_commit` and run
```
pre-commit install
```
in the repository.
