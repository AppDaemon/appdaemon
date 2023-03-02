HASS API Reference
==================

This page provides a list of API calls and specific information related to the HASS plugin.

.. _HASS App Creation:

App Creation
------------

To create apps based on just the AppDaemon base API, use some code like the following:

.. code:: python

    import hassapi as hass

    class MyApp(hass.Hass):

        def initialize(self):

.. _HASS Reference:

Reference
---------

Services
--------

.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.turn_on
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.turn_off
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.toggle
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.set_value
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.set_textvalue
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.select_option
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.notify
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.render_template

Presence
--------

.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.get_trackers
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.get_tracker_details
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.get_tracker_state
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.anyone_home
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.everyone_home
.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.noone_home

Database
--------

.. autofunction:: appdaemon.plugins.hass.hassapi.Hass.get_history

See More
---------

Read the `AppDaemon API Reference <AD_API_REFERENCE.html>`__ to learn other inherited helper functions that
can be used by Hass applications.
