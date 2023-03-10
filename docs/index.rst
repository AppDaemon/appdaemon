.. AppDaemon documentation master file, created by
   sphinx-quickstart on Fri Aug 11 14:36:18 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `doctree` directive.

Welcome to AppDaemon's documentation!
=====================================

Generated |today|

AppDaemon is a loosely coupled, multi-threaded, sandboxed python
execution environment for writing automation apps for home automation projects, and any environment that requires a robust event driven architecture.

Out of the box, AppDaemon has support for the following automation products:

- `Home Assistant <https://home-assistant.io/>`__ home automation software.
- `MQTT <http://mqtt.org/>`__ event broker.

AppDaemon also provides a configurable dashboard (HADashboard) suitable for wall mounted tablets.

A Note on Release Velocity
==========================

AppDaemon has reached a very stable point, works reliably and is fairly feature rich at this point
in its development. For that reason, releases have been slow in recent months. This does not mean that AppDaemon has been abandoned - it is used every day by
the core developers, and has an active community on Discord (see below).

Support
=======

If you have a question or need support, the following resources can help you:

- The dedicated `Home Assistant Community forum <https://community.home-assistant.io/c/third-party/appdaemon/21>`__
- Our `Discord server <https://discord.gg/qN7c7JcFjk>`_, where you are invited to join us for tips and tricks, AppDaemon discussions and general home automation!

Developers
==========

AppDaemon is developed and maintained by a small team of hard working folks:

- `Andrew Cockburn <https://github.com/acockburn>`__ - AppDaemon founder, Chief Architect and Benevolent Dictator For Life.
- `Odianosen Ejale <https://github.com/Odianosen25>`__ - Core & MQTT Development and maintenance, fixer and tester.

Contributors
^^^^^^^^^^^^

Special thanks to `Carlo Mion <https://github.com/mion00>`__ for the design and configuration of our CI pipeline and project packaging.

With thanks to previous members of the team:

- Rene Tode
- Robert Pitera
- Humberto Rodríguez Avila
- Daniel Lashua

Contents:
=========

.. toctree::
   :maxdepth: 1

   INSTALL
   CONFIGURE
   DOCKER_TUTORIAL
   HASS_TUTORIAL
   APPGUIDE
   COMMUNITY_TUTORIALS
   AD_API_REFERENCE
   HASS_API_REFERENCE
   MQTT_API_REFERENCE
   DASHBOARD_INSTALL
   DASHBOARD_CREATION
   WIDGETDEV
   DEV
   INTERNALS
   REST_STREAM_API
   UPGRADE_FROM_3.x
   UPGRADE_FROM_2.x
   HISTORY
   AD_INDEX
