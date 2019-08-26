HASS API Reference
==================

This page provides a list of API calls and specific information related to the HASS plugin.

App Creation
------------

To create apps based on just the AppDaemon base API, use some code like the following:

.. code:: python

    import hassapi as hass

    class MyApp(hass.Hass):

        def initialize(self):

Reference
---------

Services
--------

.. automethod:: appdaemon.plugins.hass.hassapi.Hass.turn_on
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.turn_off
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.toggle
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.set_value
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.set_textvalue
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.select_option
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.notify

Presence
--------

.. automethod:: appdaemon.plugins.hass.hassapi.Hass.get_trackers
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.get_tracker_details
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.get_tracker_state
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.anyone_home
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.everyone_home
.. automethod:: appdaemon.plugins.hass.hassapi.Hass.noone_home
        
Database
--------

.. automethod:: appdaemon.plugins.hass.hassapi.Hass.get_history

See More
---------

Read the `AppDaemon API Reference <AD_API_REFERENCE.html>`__ to learn other inherited helper functions that
can be used by Hass applications.