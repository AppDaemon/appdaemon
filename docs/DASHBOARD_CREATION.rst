Dashboard Creation
=======================

.. figure:: images/dash.png
   :alt: UI

   UI

Dashboard Creation
-----------------------

Dashboard configuration is simple yet very powerful. Dashboards can be
created in single files or made modular for reuse of blocks of widgets.
Dashboards are configured using YAML.

We will start with a simple single file configuration. Create a file
with a ``.dash`` extension in the ``dashboards`` directory, and pull it
up in your favorite editor.

Main Settings
~~~~~~~~~~~~~

A top level dashboard will usually have one of a number of initial
directives to configure aspects of the dashboard, although they are all
optional. An example is as follows:

.. code:: yaml

    ##
    ## Main arguments, all optional
    ##
    title: Main Panel
    widget_dimensions: [120, 120]
    widget_size: [1, 1]
    widget_margins: [5, 5]
    columns: 8
    global_parameters:
        use_comma: 0
        precision: 1
        use_hass_icon: 1

These are all fairly self explanatory:

-  ``title`` - the name that will end up in the title of the web page,
   defaults to "HADashboard".
-  ``widget_dimensions`` - the unit height and width of the individual
   widgets in pixels. Note that the absolute size is not too important
   as on tablets at least the browser will scale the page to fit. What
   is more important is the aspect ratio of the widgets as this will
   affect whether or not the dashboard completely fills the tablets
   screen. The default is [120, 120] (width, height). This works well
   for a regular iPad.
-  ``widget_size`` - the number of grid blocks each widget will be by
   default if not specified
-  ``widget_margins`` - the size of blank space between widgets.
-  ``rows`` - the total number of rows in the dashboard. This will help
   with spacing, but is optional for dashboards with fewer than 15 rows
-  ``columns`` - the number of columns the dasboard will have.
-  ``global_parameters`` - a list of parameters that will be applied to
   every widget. If the widget does not accept that parameter it will be
   ignored. Global parameters can be overriden at the widget definition
   if desired. This is useful for instance if you want to use commas as
   decimals for all of your widgets. This will also apply to widgets
   defined with just their entity ids so they will not require a formal
   widget definition just to change the decimal separator.

The very simplest dashboard needs a layout so it can understand where to
place the widgets. We use a ``layout`` directive to tell HADasboard how
to place them. Here is an example:

.. code:: yaml


    layout:
        - light.hall, light.living_room, input_boolean.heating
        - media_player(2x1), sensor.temperature

As you can see, here we are refering directly to native Home Assistant
entities. From this, HADashboard is able to figure out the right widget
type and grab it's friendly name and add it to the dasboard. For the
``clock`` and ``weather`` widgets there is no associated entity id so
just your ``clock.clock`` or ``weather.weather``.

The layout command is intended to be visual in how you lay out the
widgets. Each layout entry represents a row on the dashboard, each comma
separated widget represents a cell on that row.

Widgets can also have a size associated with them - that is the
``(2x1)`` directive appended to the name. This is simply the width of
the widget in columns and the height of the widget in rows. For
instance, ``(2x1)`` would refer to a widget 2 cells wide and 1 cell
high. If you leave of the sizing information, the widget will use the
``widget_size`` dashboard parameter if specified, or default to
``(1x1)`` if not. HADasboard will do it's best to calculate the right
layout from what you give it but expect strange behavior if you add too
many widgets on a line.

For a better visual cue you can lay the widgets out with appropriate
spacing to see what the grid will look like more intuitively:

.. code:: yaml

     layout:
        - light.hall,       light.living_room, input_boolean.heating
        - media_player(2x1),                   sensor.temperature

... and so on.

Make sure that the number of widths specified adds up to the total
number of columns, and don't forget to take into account widgets that
are more than one row high (e.g. the weather widget here).

If you want a blank space you can use the special widget name
``spacer``. To leave a whole row empty, just leave an entry for it with
no text. For instance:

.. code:: yaml

        - light.hall, light.living_room, input_boolean.heating
        -
        - media_player(2x1), sensor.temperature

The above would leave the 2nd row empty. If you want more than one empty
line use ``empty`` as follows":

.. code:: yaml

        - light.hall, light.living_room, input_boolean.heating
        - empty: 2
        - media_player(2x1), sensor.temperature

This would leave the 2nd and 3rd rows empty.

And that is all there to it, for a simple one file dashboard.

Detailed Widget Definition
~~~~~~~~~~~~~~~~~~~~~~~~~~

The approach above is ok for simple widgets like lights, but HADashboard
has a huge range of customization options. To access these, you need to
formally define the widget along with its associated parameters.

To define a widget simply add lines elsewhere in the file. Give it a
name , a widget type and a number of optional parameters like this:

.. code:: yaml

    weather_widget:
        widget_type: weather
        units: "&deg;F"

Here we have defined a widget of type "weather", and given it an
optional parameter to tell it what units to use for temperature. Each
widget type will have different required parameters, refer to the
documentation below for a complete list for each type. All widgets
support ways to customize colors and text sizes as well as attibutes
they need to understand how to link the widget to Home Assistant, such
as entity\_ids.

Lets look at a couple more examples of widget definitions:

.. code:: yaml

    clock:
        widget_type: clock

    weather:
        widget_type: weather
        units: "&deg;F"
        
    side_temperature:
        widget_type: sensor
        title: Temperature
        units: "&deg;F"
        precision: 0
        entity: sensor.side_temp_corrected

    side_humidity:
        widget_type: sensor
        title: Humidity
        units: "%"
        precision: 0
        entity: sensor.side_humidity_corrected

    andrew_presence:
        widget_type: device_tracker
        title: Andrew
        device: andrews_iphone

    wendy_presence:
        widget_type: device_tracker
        title: Wendy
        device: wendys_iphone

    mode:
        widget_type: sensor
        title: House Mode
        entity: input_select.house_mode

    light_level:
        widget_type: sensor
        title: Light Level
        units: "lux"
        precision: 0
        shorten: 1
        entity: sensor.side_multisensor_luminance_25_3
            
    porch_motion:
        widget_type: binary_sensor
        title: Porch
        entity: binary_sensor.porch_multisensor_sensor_27_0

    garage:
        widget_type: switch
        title: Garage
        entity: switch.garage_door
        icon_on: fa-car
        icon_off: fa-car
        warn: 1

Now, instead of an entity id we refer to the name of the widgets we just
defined:

.. code:: yaml


    layout:
        - clock(2x1), weather(2x2), side_temperature(1x1), side_humidity(1x1), andrew_presence(1x1), wendy_presence(1x1)
        - mode(2x1), light_level(2x1), porch_motion(1x1), garage(1x1)

It is also possible to add a widget from a standalone file. The file
will contain a single widget definition. To create a clock widget this
way we would make a file called ``clock.yaml`` and place it in the
dashboard directory along with the dashboard. The contents would look
something like this:

.. code:: yaml

    widget_type: clock
    widget_style: "color: red"

Note that the indentation level starts at 0. To include this file, just
reference a widget called ``clock`` in the layout, and HADashboard will
automatically load the widget.

A file will override a native entity, so you can create your dashboard
just using entities, but if you want to customize a specific entity, you
can just create a file named ``<entity_name>.yaml`` and put the settings
in there. You can also override entity names by specifying a widget of
that name in the same or any other file, which will take priority over a
standalone yaml file.

And that is all there to it, for a simple one file dashboard.

Advanced Dashboard Definition
-----------------------------

When you get to the point where you have multiple dashboards, you may
want to take a more modular approach, as you will find that in many
cases you want to reuse parts of other dashboards. For instance, I have
a common header for mine consisting of a row or two of widgets I want to
see on every dashboard. I also have a footer of controls to switch
between dashboards that I want on each dashboard as well.

To facilitate this, it is possible to include additional files, inline
to build up dashboards in a more modular fashion. These additional files
end in ``.yaml`` to distinguish them from top level dashboards. They can
contain additional widget definitions and also optionally their own
layouts.

The sub files are included in the layout using a variation of the layout
directive:

.. code:: yaml

    layout:
        - include: top_panel

This will look for a file called ``top_panel.yaml`` in the dashboards
directory, then include it. There are a couple of different ways this
can be used.

-  If the yaml file includes it's own layouts directive, the widgets
   from that file will be placed as a block, in the way described by its
   layout, making it reusable. You can change the order of the blocks
   inclusion by moving where in the original layout directive you
   include them.
-  If the yaml file just includes widget definitions, it is possible to
   perform the layout in the higher level dash if you prefer so you
   still get an overall view of the dashboard. This approach has the
   benefit that you can be completely flexible in the layout wheras the
   first method defines fixed layouts for the included blocks.

I prefer the completely modular approach - here is an example of a full
top level dashboard created in that way:

.. code:: yaml

    title: Main Panel
    widget_dimensions: [120, 120]
    widget_margins: [5, 5]
    columns: 8

    layout:
        - include: top_panel
        - include: main_middle_panel
        - include: mode_panel
        - include: bottom_panel

As you can see, it includes four modular sub-dashes. Since these pieces
all have their own layout information there is no need for additional
layout in the top level file. Here is an example of one of the self
contained sub modules (mode\_panel.yaml):

.. code:: yaml

    clock:
        widget_type: clock

    weather:
        widget_type: weather
        units: "&deg;F"

    side_temperature:
        widget_type: sensor
        title: Temperature
        units: "&deg;F"
        precision: 0
        entity: sensor.side_temp_corrected

    side_humidity:
        widget_type: sensor
        title: Humidity
        units: "%"
        precision: 0
        entity: sensor.side_humidity_corrected

    andrew_presence:
        widget_type: device_tracker
        title: Andrew
        device: andrews_iphone

    wendy_presence:
        widget_type: device_tracker
        title: Wendy
        device: dedb5e711a24415baaae5cf8e880d852

    mode:
        widget_type: sensor
        title: House Mode
        entity: input_select.house_mode

    light_level:
        widget_type: sensor
        title: Light Level
        units: "lux"
        precision: 0
        shorten: 1
        entity: sensor.side_multisensor_luminance_25_3
            
    porch_motion:
        widget_type: binary_sensor
        title: Porch
        entity: binary_sensor.porch_multisensor_sensor_27_0

    garage:
        widget_type: switch
        title: Garage
        entity: switch.garage_door
        icon_on: fa-car
        icon_off: fa-car
        warn: 1

    layout:
        - clock(2x1), weather(2x2), side_temperature, side_humidity, andrew_presence, wendy_presence
        - mode(2x1), light_level(2x1), porch_motion, garage

Now if we take a look at that exact same layout, but assume that just
the widget definitions are in the sub-blocks, we would end up with
something like this - note that we must explicitly lay out each widget
we have included in the other files:

.. code:: yaml

    title: Main Panel
    widget_dimensions: [120, 120]
    widget_margins: [5, 5]
    columns: 8

    layout:
        - include: top_panel
        - include: main_middle_panel
        - include: mode_panel
        - include: bottom_panel
        - clock(2x1), weather(2x2), side_temperature, side_humidity, andrew_presence, wendy_presence
        - mode(2x1), light_level(2x1), porch_motion, garage
        - wlamp_scene, don_scene, doff_scene, dbright_scene, upstairs_thermometer, downstairs_thermometer, basement_thermometer, thermostat_setpoint  
        - obright_scene, ooff_scene, pon_scene, poff_scene, night_motion, guest_mode, cooling, heat
        - morning(2x1), day(2x1), evening(2x1), night(2x1)
        - load_main_panel, load_upstairs_panel, load_upstairs, load_downstairs, load_outside, load_doors, load_controls, reload  

In this case, the actual layout including a widget must be after the
include as you might expect.

A few caveats for loaded sub files:

-  Sub files can include other subfiles to a maximum depth of 10 -
   please avoid circular references!
-  When layout information is included in a sub file, the subfile must
   comprise 1 or more complete dashboard rows - partial rows or blocks
   are not supported.

As a final option, you can create widget definitions in the main file
and use them in the layout of the header/footer/etc. For example, if you
have a header that has a label in it that lists the room that the
dashboard is associated with, you can put the label widget definition in
the header file but all the pages get the same message. If you put the
label widget definition in the main file for the room, and reference it
from the layout in the header, each page has the right name displayed in
the header.

For example:

.. code:: yaml

    clock:
        widget_type: clock
    layout:
        - label(2x2),clock(2x2)

In this example of a header, we reference a clock and a label in the
layout. We can re-use this header, but in order to make the label change
for every page we use it on we actually define it in the dashboard file
itself, and include the header in the layout:

.. code:: yaml

    title: Den Panel
    widget_dimensions: [120, 120]
    widget_margins: [5, 5]
    columns: 8

    label:
        widget_type: label
        text: Welcome to the Den
        
    layout:
        - include: header

Widget Customization
--------------------

Widgets allow customization using arbitary CSS styles for the individual
elements that make up the widget. Every widget has a
\`\ ``widget_style`` argument to apply styles to the whole widget, as
well as one or more additional style arguments that differ for each
widget. To customize a widget background for instance:

.. code:: yaml

    clock:
      widget_type: clock
      widget_style: "background: white;"

As is usual with CSS you can feed it multiple parameters at once, e.g.:

.. code:: yaml

    clock:
      widget_type: clock
      widget_style: "background: white; font-size: 150%;"

You can use any valid CSS style here although you should probably steer
away from some of the formatting types as they may interact badly with
HADasboards formatting. Widget level styles will correctly override just
the style in the skin they are replacing.

In the case of the clock widget, it also supports ``date_style`` and
``time_style`` to modify those elements accordingly:

.. code:: yaml

    clock:
      widget_type: clock
      widget_style: "background: white"
      date_style: "color: black"
      time_style: "color: green"

Since ``date_style`` and ``time_style`` are applied to more specific
elements, they will override ``widget_style``. Also note that some
widget styles may be specified in the widget's CSS, in which case that
style will override ``widget_style`` but not the more specific styles.

State and state text
--------------------

Some widgets allow you to display not only an icon showing the state but
also text of the state itself. The following widgets allow this:

-  scene
-  binary\_sensor
-  switch
-  device\_tracker
-  script
-  lock
-  cover
-  input\_boolean

In order to enable this, just add:

.. code:: yaml

    state_text: 1

to the widget definition. This will then make the widget show the HA
state below the icon. Since native HA state is not always very pretty it
is also possible to map this to better values, for instance in a
different language than English.

To add a state map, just add a state\_map list to the widget definition
listing the HA states and what you actually want displayed. For
instance:

.. code:: yaml

    state_map:
      "on": Aan
      "off": Uit

One wrinkle here is that YAML over enthusiastically "helps" by
interpreting things like ``on`` and ``off`` as booleans so the quotes
are needed to prevent this.

Icons
-----

Widgets that allow the specification of icons have access to both `Font
Awesome <http://fontawesome.io/cheatsheet/>`__ and `Material
Design <https://materialdesignicons.com/>`__ Icons. To specify an icon
simply use the prefix ``fa-`` for Font Aweesome and ``mdi-`` for
Material Design. e,g,:

.. code:: yaml

    icon_on: fa-alert
    icon_off: mdi-cancel

In addition, the widget can be configured to use whatever icon is
defined for it in Home Assistant by setting the parameter:

.. code:: yaml

    use_hass_icon: 1

This can also be set at the dashboard level as a global parameter.

External Commands
-----------------

The dashboard can accept command from external systems to prompt
actions, such as navigation to different pages. These can be achieved
through a variety of means:

-  AppDaemon API Calls
-  HASS Automations/Scripts
-  Alexa Intents

The mechanism used for this is HASS custom events. AppDaemon has it's own
API calls to handle these events, for further details see the
`AppDaemon API Pages <API.html>`__. The custom event name is ``hadashboard`` and the
dashboard will respond to various commands with associated data.

To create a suitable custom event within a HASS automation, script or
Alexa Intent, simply define the event and associated data as follows
(this is a script example):

.. code:: yaml

    alias: Navigate
    sequence:
    - event: hadashboard
      event_data:
        command: navigate
        timeout: 10
        target: SensorPanel

The current list of commands supported and associated arguments are as
follows:

navigate
~~~~~~~~

Force any connected dashboards to navigate to a new page

Arguments
^^^^^^^^^

``target`` - Name of the new Dashboard to navigate to, e.g.
``SensorPanel`` - this is not a URL. ``timeout`` - length of time to
stay on the new dashboard before returning to the original. This
argument is optional and if not specified, the navigation will be
permanent.

Note that if there is a click or touch on the new panel before the
timeout expires, the timeout will be cancelled.

``timeout`` - length of time to stay on the new dashboard ``return`` -
dashboard to return to after the timeout has elapsed.

Widget Reference
----------------

Here is the current list of widgets and their description and supported
parameters:

clock
~~~~~

A simple 12 hour clock with the date. Not currently very customizable
but it will be improved upon.

Mandatory arguments:
^^^^^^^^^^^^^^^^^^^^

None

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``time_format`` - set to "24hr" if you want military time/24 hour
   clock
-  ``show_seconds`` - set to 1 if you want to see seconds on the display

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``time_style``
-  ``date_style``

weather
~~~~~~~

Up to date weather reports. Requires dark sky to be configured in Home
Assistant with at minimum the following sensors:

-  temperature
-  humidity
-  precip\_probability
-  precip\_intensity
-  wind\_speed
-  pressure
-  wind\_bearing
-  apparent\_temperature
-  icon

Mandatory arguments:
^^^^^^^^^^^^^^^^^^^^

None

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

None

Cosmetic Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``main_style``
-  ``unit_style``
-  ``sub_style``

sensor
~~~~~~

A widget to report on values for any sensor in Home Assistant

The widget will detect whether or not it is showing a numeric value, and
if so, it will use the numeric style. If it is showing text it will use
the text style, which among other things makes the text size smaller.

Mandatory Arguments:
^^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the sensor to be monitored

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``units`` - the unit symbol to be displayed, if not specified HAs
   unit will be used, specify "" for no units
-  ``precision`` - the number of decimal places
-  ``shorten`` - if set to one, the widget will abbreviate the readout
   for high numbers, e.g. ``1.1K`` instead of ``1100``
-  ``use_comma`` - if set to one\`, a comma will be used as the decimal
   separator
-  ``state_map``
-  ``sub_entity`` - second entity to be displayed in the state text area
-  ``sub_entity_map`` - state map for the sub\_entity

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``value_style``
-  ``text_style``
-  ``unit_style``

rss
~~~

A widget to display an RSS feed.

Note that the actual feeds are configured in appdaemon.yaml as follows:

.. code:: yaml

    AppDaemon:

      rss_feeds:
        - feed: <feed_url>
          target: <target_name>
        - feed: <feed url>
          target: <target_name>

          ...

      rss_update: <feed_refresh_interval>

-  ``feed_url`` - fully qualified path to rss feed, e.g.
   ``http://rss.cnn.com/rss/cnn_topstories.rss``
-  ``target name`` - the entity of the target RSS widget in the
   dashboard definition file
-  ``feed_refresh_interval`` - how often AppDaemon will refresh the RSS
   feeds

There is no limit to the number of feeds you configure, and you will
need to configure one RSS widget to display each feed.

The RSS news feed cannot be configured if you are still using the legacy
``.cfg`` file type.

Mandatory Arguments:
^^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the name of the configured feed - this must match the
   ``target_name`` configured in the AppDaemon configuration
-  ``interval`` - the period between display of different items within
   the feed

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``recent`` - the number of most recent stories that will be shown. If
   not specified, all stories in the feed will be shown.

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``text_style``

gauge
~~~~~

A widget to report on numeric values for sensors in Home Assistant in a
gauge format.

Mandatory Arguments:
^^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the sensor to be monitored
-  ``max`` - maximum value to show
-  ``min`` - minimum value to show

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``units`` - the unit symbol to be displayed, if not specified HAs
   unit will be used, specify "" for no units

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``low_color``
-  ``med_color``
-  ``high_color``
-  ``bgcolor``
-  ``color``

Note that unlike other widgets, the color settings require an actual
color, rather than a CSS style.

device\_tracker
~~~~~~~~~~~~~~~

A Widget that reports on device tracker status. It can also be
optionally be used to toggle the status between "home" and "not\_home".

Mandatory Arguments:
^^^^^^^^^^^^^^^^^^^^

-  ``device`` - name of the device from ``known_devices.yaml``, *not*
   the entity\_id.

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``enable`` - set to 1 to enable the widget to toggle the
   device\_tracker status
-  ``state_text``
-  ``state_map``
-  ``active_map``

Active map is used to specify states other than "home" that will be
regarded as active, meaning the icon will light up. This can be useful
if tracking a device tracker within the house using beacons for
instance.

Example:

.. code:: yaml

    wendy_presence_mapped:
      widget_type: device_tracker
      title: Wendy
      title2: Mapped
      device: wendys_iphone
      active_map:
        - home
        - house
        - back_yard
        - upstairs

In the absence of an active map, only the state ``home`` will be
regarded as active.

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``
-  ``state_text_style``

label
~~~~~

A widget to show a simple static text string

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

None

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``text`` - the text displayed on the tile

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``text_style``

scene
~~~~~

A widget to activate a scene

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the scene

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

script
~~~~~~

A widget to run a script

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the script

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

mode
~~~~

A widget to track the state of an ``input_select`` by showing active
when it is set to a specific value. Also allows scripts to be run when
activated.

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the ``input_select``
-  ``mode`` - value of the input select to show as active
-  ``script`` - script to run when pressed
-  ``state_text``
-  ``state_map``

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

switch
~~~~~~

A widget to monitor and activate a switch

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the switch

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

lock
~~~~

A widget to monitor and activate a lock

Note that unlike HASS, Dashboard regards an unlocked lock as active. By
contrast, the HASS UI shows a locked lock as "on". Since the purpose of
the dashboard is to alert at a glance on anything that is unusual, I
chose to make the unlocked state "active" which means in the default
skin it is shown as red, wheras a locked icon is shown as gray. You can
easily change this behavior by setting active and inactive styles if you
prefer.

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the lock

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

cover
~~~~~

A widget to monitor and activate a cover. At this time only the open and
close actions are supported.

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the cover

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

input\_boolean
~~~~~~~~~~~~~~

A widget to monitor and activate an input\_boolean

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the input\_boolean

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

binary\_sensor
~~~~~~~~~~~~~~

A widget to monitor a binary\_sensor

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the binary\_sensor

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``state_text``
-  ``state_map``

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``widget_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``title_style``
-  ``title2_style``

light
~~~~~

A widget to monitor and contol a dimmable light

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the light

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``icon_on``
-  ``icon_off``
-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``on_attributes`` - a list of supported HA attributes to set as
   initial values for the light.

Note that ``rgb_color`` and ``xy_color`` are not specified with list
syntac as in Home Assistant scenes. See below for examples.

e.g.

.. code:: yaml

    testlight2:
        widget_type: light
        entity: light.office_2
        title: office_2
        on_attributes:
            brightness: 100
            color_temp: 250

or:

.. code:: yaml

    testlight2:
        widget_type: light
        entity: light.office_2
        title: office_2
        on_attributes:
            brightness: 100
            rgb_color: 128, 34, 56

or:

.. code:: yaml

    testlight2:
        widget_type: light
        entity: light.office_2
        title: office_2
        on_attributes:
            brightness: 100
            xy_color: 0.4, 0.9

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``icon_on``
-  ``icon_off``
-  ``icon_up``
-  ``icon_down``
-  ``title_style``
-  ``title2_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``text_style``
-  ``level_style``
-  ``level_up_style``
-  ``level_down_style``

input\_slider
~~~~~~~~~~~~~

A widget to monitor and contol an input slider

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the input\_slider

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``step`` - the size of step in brightness when fading the slider up
   or down
-  ``units`` - the unit symbol to be displayed
-  ``use_comma`` - if set to one, a comma will be used as the decimal
   separator

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``icon_up``
-  ``icon_down``
-  ``title_style``
-  ``title2_style``
-  ``text_style``
-  ``level_style``
-  ``level_up_style``
-  ``level_down_style``

climate
~~~~~~~

A widget to monitor and contol a climate entity

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the climate entity

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``step`` - the size of step in temperature when fading the slider up
   or down
-  ``units`` - the unit symbol to be displayed

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``icon_up``
-  ``icon_down``
-  ``title_style``
-  ``title2_style``
-  ``text_style``
-  ``level_style``
-  ``level_up_style``
-  ``level_down_style``

media\_player
~~~~~~~~~~~~~

A widget to monitor and contol a media player

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the media player

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``truncate_name`` - if specified, the name of the media will be
   truncated to this length.
-  ``step`` - the step (in percent) that the volume buttons will use.
   (default, 10%)

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``icon_on``
-  ``icon_off``
-  ``icon_up``
-  ``icon_down``
-  ``title_style``
-  ``title2_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``text_style``
-  ``level_style``
-  ``level_up_style``
-  ``level_down_style``

group
~~~~~

A widget to monitor and contol a group of lights

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the group

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text
-  ``monitored_entity`` - the actual entity to monitor

Groups currently do no report back state changes correctly when
attributes light brightness are changed. As a workaround, instead of
looking for state changes in the group, we use ``monitored_entity``
instead. This is not necessary of there are no dimmable lights in the
group, however if there are, it should be set to the entity\_id of one
of the dimmable group members.

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``icon_on``
-  ``icon_off``
-  ``icon_up``
-  ``icon_down``
-  ``title_style``
-  ``title2_style``
-  ``icon_style_active``
-  ``icon_style_inactive``
-  ``text_style``
-  ``level_style``
-  ``level_up_style``
-  ``level_down_style``

navigate
~~~~~~~~

A widget to navgigate to a new URL, intended to be used for switching
between dashboards

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``url`` - a url to navigate to. Use a full URL including the "http"
   part.
-  ``dashboard`` - a dashboard to navigate to e.g. ``MainPanel``
-  ``title`` - the title displayed on the tile
-  ``args`` - a list of arguments.
-  ``skin`` - Skin to use with the new screen (for HADash URLs only)

For an arbitary URL, Args can be anything. When specifying a dashboard
parameter, args have the following meaning:

``timeout`` - length of time to stay on the new dashboard ``return`` -
dashboard to return to after the timeout has elapsed.

Both ``timeout`` and ``return`` must be specified.

If adding arguments use the args variable do not append them to the URL
or you may break skinning. Add arguments like this:

.. code:: yaml

    some_widget:
        widget_type: navigate
        title: Amazon
        url: http://amazon.com
        args:
          arg1: fred
          arg2: jim

or:

.. code:: yaml

    some_widget:
        widget_type: navigate
        title: Sensors
        dashboard: Sensors
        args:
          timeout: 10
          return: Main

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_active``
-  ``icon_inactive``
-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``icon_style``

reload
~~~~~~

A widget to reload the current dashboard.

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

None.

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``icon_active``
-  ``icon_inactive``
-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``icon_active_style``
-  ``icon_inactive_style``

iframe
~~~~~~

A widget to display other content within the dashboard

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``url_list`` - a list of 1 or more URLs to cycle though. or
-  ``img_list`` - a list of 1 or more Image URLs to cycle through.

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``refresh`` - (seconds) if set, the iframe widget will progress down
   it's list every refresh period, returning to the beginning when it
   hits the end. Use this in conjunction with a single entry in the
   ``url_list`` to have a single url refresh at a set interval.

For regular HTTP sites, use the ``url_list`` argument, for images the
``img_list`` argument should work better.

Example:

.. code:: yaml

    iframe:
        widget_type: iframe
        title: Cats
        refresh: 60
        url_list: 
          - https://www.pexels.com/photo/grey-and-white-short-fur-cat-104827/
          - https://www.pexels.com/photo/eyes-cat-coach-sofa-96938/
          - https://www.pexels.com/photo/silver-tabby-cat-lying-on-brown-wooden-surface-126407/
          - https://www.pexels.com/photo/kitten-cat-rush-lucky-cat-45170/
          - https://www.pexels.com/photo/grey-fur-kitten-127028/
          - https://www.pexels.com/photo/cat-whiskers-kitty-tabby-20787/
          - https://www.pexels.com/photo/cat-sleeping-62640/

Content will be shown with scroll bars which can be undesirable. For
images this can be alleviated by using an image resizing service such as
the one offered by
`Google <https://carlo.zottmann.org/posts/2013/04/14/google-image-resizer.html>`__.

.. code:: yaml

    weather_frame:
        widget_type: iframe
        title: Radar
        refresh: 300
        frame_style: ""
        img_list: 
          - https://images1-focus-opensocial.googleusercontent.com/gadgets/proxy?url=https://icons.wxug.com/data/weather-maps/radar/united-states/hartford-connecticut-region-current-radar-animation.gif&container=focus&refresh=240&resize_h=640&resize_h=640
          - https://images1-focus-opensocial.googleusercontent.com/gadgets/proxy?url=https://icons.wxug.com/data/weather-maps/radar/united-states/bakersfield-california-region-current-radar.gif&container=focus&refresh=240&resize_h=640&resize_h=640

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``

camera
~~~~~~

A widget to display a refreshing camera image on the dashboard

Mandatory Arguments
^^^^^^^^^^^^^^^^^^^

-  ``entity_picture``

This can be found using the developer tools, and will be one of the
parameters associated with the camera you want to view. If you are using
a password, you will need to append ``&api_password=<your password>`` to
the end of the entity\_picture. It will look something like this:

``http://192.168.1.20:8123/api/camera_proxy/camera.living_room?token=<your token>&api_password=<redacted>``

If you are using SSL, remeber to use the full DNS name and not the IP
address.

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``refresh`` - (seconds) if set, the camera image will refresh every
   interval.

Cosmetic Arguments
^^^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``

alarm
~~~~~

A widget to report on the state of an alarm and allow code entry

Mandatory Arguments:
^^^^^^^^^^^^^^^^^^^^

-  ``entity`` - the entity\_id of the alarm to be monitored

Optional Arguments:
^^^^^^^^^^^^^^^^^^^

-  ``title`` - the title displayed on the tile
-  ``title2`` - a second line of title text

Style Arguments:
^^^^^^^^^^^^^^^^

-  ``widget_style``
-  ``title_style``
-  ``title2_style``
-  ``state_style``
-  ``panel_state_style``
-  ``panel_code_style``
-  ``panel_background_style``
-  ``panel_button_style``

Skins
-----

HADashboard fully supports skinning and ships with a number of skins. To
access a specific skin, append the parameter ``skin=<skin name>`` to the
dashboard URL. Skin names are sticky if you use the Navigate widet to
switch between dashboards and will stay in force until another skin or
no skin is specified.

HADasboard currently has the following skins available:

-  default - the classic HADashboard skin, very simple
-  obsidian, contributed by ``@rpitera``
-  zen, contributed by ``@rpitera``
-  simplyred, contributed by ``@rpitera``
-  glassic, contributed by ``@rpitera``

Skin development
----------------

HADashboard fully supports customization through skinning. It ships with
a number of skins courtesy of @rpitera, and we encourage users to create
new skins and contribute them back to the project.

To create a custom skin you will need to know a little bit of CSS. Start
off by creating a directory called ``custom_css`` in the configuration
directory, at the same level as your dashboards directory. Next, create
a subdirectory in ``custom_css`` named for your skin.

The skin itself consists of 2 separate files:

-  ``dashboard.css`` - This is the base dashboard CSS that sets widget
   styles, background look and feel etc.
-  ``variables.yaml`` - This is a list of variables that describe how
   different elements of the widgets will look. Using the correct
   variables you can skin pretty much every element of every widget
   type.

Dashboard.css is a regular css file, and knowledge of CSS is required to
make changes to it.

Variables.yaml is really a set of overrise styles, so you can use
fragments of CSS here, basically anything that you could normally put in
an HTML ``style`` tag. Variables .yaml also supports variable expansion
to make structuring the file easier. Anything that starts with a ``$``
is treated as a variable that refers back to one of the other yaml
fields in the file.

Here is an example of a piece of a variables.yaml file:

.. code:: yaml

    ##
    ## Styles
    ##

    white: "#fff"
    red: "#ff0055"
    green: "#aaff00"
    blue: "#00aaff"
    purple: "#aa00ff"
    yellow: "#ffff00"
    orange: "#ffaa00"

    gray_dark: "#444"
    gray_medium: "#666"
    gray_light: "#888"

    ##Page and widget defaults
    background_style: ""
    text_style: ""

    ##These are used for icons and indicators
    style_inactive: "color: $gray_light"
    style_active: "color: gold"
    style_active_warn: "color: gold"
    style_info: "color: gold; font-weight: 500; font-size: 250%"
    style_title: "color: gold; font-weight: 900"
    style_title2: "color: $white"

Here we are setting up some general variables that we can reuse for
styling the actual widgets.

Below, we are setting styles for a specific widget, the light widget.
All entries are required but can be left blank by using double quotes.

.. code:: yaml

    light_icon_on: fa-circle
    light_icon_off: fa-circle-thin
    light_icon_up: fa-plus
    light_icon_down: fa-minus
    light_title_style: $style_title
    light_title2_style: $style_title2
    light_icon_style_active: $style_active
    light_icon_style_inactive: $style_inactive
    light_state_text_style: $white
    light_level_style: "color: $gray_light"
    light_level_up_style: "color: $gray_light"
    light_level_down_style: "color: $gray_light"
    light_widget_style: ""

Images can be included - create a sub directory in your skin directory,
call it ``img`` or whatever you like, then refer to it in the css as:

``/custom_css/<skin name>/<image directory>/<image filename>``

One final feature is the ability to include additional files in the
header and body of the page if required. This can be useful to allow
additional CSS from 3rd parties or include JavaScript.

Custom head includes - should be a YAML List inside ``variables.yaml``,
e.g.:

.. code:: yaml

    head_includes:
      - some include
      - some other include

Text will be included verbatim in the head section of the doc, use for
styles, javascript or 3rd party css etc. etc. It is your responsibility
to ensure the HTML is correct

Similarly for body includes:

.. code:: yaml

    body_includes:
      - some include
      - some other include

To learn more about complete styles, take a look at the supplied styles
to see how they are put together. Start off with the ``dashboard.css``
and ``variables.yaml`` from an exisitng file and edit to suit your
needs.

Example Dashboards
------------------

Some example dashboards are available in the AppDaemon repository:

`Dashboards <https://github.com/home-assistant/appdaemon/tree/dev/conf/example_dashboards>`__
