# Description

AppDaemon is a loosely coupled, multi-threaded, sandboxed python
execution environment for writing automation apps for various types of Home Automation Software including [Home
Assistant](https://home-assistant.io/) and MQTT. It has a pluggable architecture allowing it to be integrated with
practically any event driven application.

It also provides a configurable dashboard (HADashboard)
suitable for wall mounted tablets.

For full instructions on installation and use check out the [AppDaemon Project Documentation](http://appdaemon.readthedocs.io).


## Development of the AppDaemon library

We use [pre-commit](https://pre-commit.com) for linting of the code, so `pip install pre_commit` and run
```
pre-commit install
```
in the repository.
