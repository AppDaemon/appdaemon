HADashboard Widget Development
==============================

HADashboard supports a full Widget API intended to simplify the creation of 3rd party widgets.
In this guide, we will describe the APIs and requirements for a widget, the workflow for widget creation,
and suggestions on how to contribute widgets back to HADashboard.

What is a Widget?
-----------------

A widget is a contained piece of functionality that can be placed on a Dashboard.
In many cases, widgets refer to types of devices that can be controlled via Home Assistant,
but also, widgets can be unrelated, for instance an RSS widget.

There are two main types of widgets, ``Base Widgets`` and ``Derived Widgets``.
Base Widgets contain all of the HTML, CSS and JavaScript code to render and run the widget,
whereas Derived Widgets are just a structured list of variables that are passed down to Base Widgets.
Base Widgets live in subdirectories, Derived Widgets are simply yaml files.

The reason for the 2 types of widget is one of design philosophy. The goal is to have relatively few
Base Widgets, and multiple derived widgets that map to them with minor parameter changes.
For example, in Home Assistant, a light and a group are fairly similar, and require identical controls and status displays.
This makes it possible to create a single Base Widget, and map to it with two separate Derived Widgets.
When creating a new Widget type, attempt to do one of the following in order of preference:

#. Create a new Derived Widget that works with an existing Base Widget
#. Create a new Derived Widget that works with modifications to an existing Base Widget
#. Create a new Derived and Base Widget

We also talk abour a third type of widgets, an ``Instantiated Widget`` -
this refers to an actual widget in a dashboard configuration file which will have a widget type and a number of
specific variables.

Creating Custom Widgets
-----------------------

When creating new widgets, in a similar way to custom skins,
HADashboard allows the creation of a directory called ``custom_widgets`` in the configuration directory.
Any yaml files placed in here will be treated as new Derived Widgets.
Any directories here will be treated as new Base Widgets.
If you are creating a new widget you will need to use a new name for the widget.
Base Widgets by convention are stored in directories
that are named starting with ``base`` e.g. ``baselight``, or ``basesuperwidget``.

If either a Derived Widget or Base Widget have the same name as an existing widget,
the custom widget will be used in preference to allow existing widgets to be easily modified.

When a widget has been created and tested, and the author desires to contribute the widget back to the community,
all that is required is that the Derived and Base Widgets are placed in the Git Repository in the standard widget directory
(``appdaemon/widgets``) then a Pull Request may be issued in the ususal way.

Derived Widgets
---------------

A derived widget is simply a ``yaml`` file with a number of known fields to describe the widget.
A secondary function of derived widgets is to map in CSS variables for skinning.

Lets start with an example - here is the derived widget code for the light widget:

.. code:: yaml

    widget_type: baselight
    entity: {{entity}}
    post_service_active:
      service: homeassistant/turn_on
      entity_id: {{entity}}
    post_service_inactive:
      service: homeassistant/turn_off
      entity_id: {{entity}}
    fields:
      title: {{title}}
      title2: {{title2}}
      icon: ""
      units: "%"
      level: ""
      state_text: ""
      icon_style: ""
    icons:
      icon_on: $light_icon_on
      icon_off: $light_icon_off
    static_icons:
      icon_up: $light_icon_up
      icon_down: $light_icon_down
    css:
      icon_style_active: $light_icon_style_active
      icon_style_inactive: $light_icon_style_inactive
    static_css:
      title_style: $light_title_style
      title2_style: $light_title2_style
      state_text_style: $light_state_text_style
      level_style: $light_level_style
      unit_style: $light_unit_style
      level_up_style: $light_level_up_style
      level_down_style: $light_level_down_style
      widget_style: $light_widget_style


Lets break it down line by line.

Top Level Variables
~~~~~~~~~~~~~~~~~~~

.. code:: yaml

    widget_type: baselight
    entity: {{entity}}

Any entries at the top level are simply variables to be passed to the Base Widget. Some of them have special meanings
(listed in the following sections) but any values are allowed, and are all passed to the Base Widget.
The exception to this is the ``widget_type`` entry, which is required and refers to the Base Widget that this Derived
Widget works with.

In the example above, ``entity`` is an argument that will be made available to the base widget.
The value, ``{{entity}}`` is a simple passthrough from the Instantiated Widget in the Dashboard.
The significance of this is that a Derived Widget may want to hard code specific parameters while passing others through.
For example, a Base Widget may require a ``service`` parameter for which service to call to turn a device on.
A ``switch`` Derived Widget may hard code this as ``switch.turn_on`` while a ``light`` derived widget may hard code it
as ``light.turn_on``. Both however require the entity name from the Instantiated widget.
In practice, this example is somewhat artificial as you could use ``home_assistant.turn_on`` for both service calls,
and in fact lights and switches have different Base Widgets, but the concept remains valid.

An example of the above can be seen in action here:

.. code:: yaml

    post_service_active:
      service: homeassistant/turn_on
      entity_id: {{entity}}
    post_service_inactive:
      service: homeassistant/turn_off
      entity_id: {{entity}}

``post_service_active`` and ``post_service_inactive`` are both parameters specific to the baselight Base Widget.

The remaining parameters have special significance and provide required information for the Base Widget.

Fields
~~~~~~

.. code:: yaml

    fields:
      title: {{title}}
      title2: {{title2}}
      icon: ""
      units: "%"
      level: ""
      state_text: ""
      icon_style: ""

Entries in the fields arguments map directly to the HTML fields declared in the Base Widget and must all be present.
Any field that has a defined value will be used to automatically initialize the corresponding value in the widget.
This is useful for static fields such as titles and simplifies the widget code significantly.
Fields that are not required to be initialized must still be present and set to ``""``.
Again, it is possible to map values directly from the Instantiated Widget straight through to the Base Widget.

Icons
~~~~~

.. code:: yaml

    icons:
      icon_on: $light_icon_on
      icon_off: $light_icon_off

The icons parameter refers to icons that may be in use in the Base Widget.
The names must match what the Base Widget is expecting.
These Icons are expected to be manipulated by the Base Widget and are provided as specific arguments to it.
Whilst it is possible to hard code these, the intended use here is to use variables as above.
These variables map back to variables in the skin in use and are duplicated,
possibly with different values in different skins.

The corresponding skin entries for these in the default skin are:

.. code:: yaml

    light_icon_on: fa-circle
    light_icon_off: fa-circle-thin

These could be different in another skin.

In the base widget, there is code to change the icon from the on icon to the off icon in response to a
touch or a state change triggered elsewhere.
The Base Widget has access to theses icon names when executing that code.

Static Icons
~~~~~~~~~~~~

.. code:: yaml

    static_icons:
      icon_up: $light_icon_up
      icon_down: $light_icon_down

Static icons are similar in concept to fields in that they map directly to fields in the widget and will be
prepopulated automatically under the assumption that they don't need to change.
As with the icons, the actual values are mapped in the skin.

An example of a static icon might be the plus and minus icons on the climate widget -
they may be different in other skins but don't need to change once the widget is initialized.

CSS
~~~

.. code:: yaml

    css:
      icon_style_active: $light_icon_style_active
      icon_style_inactive: $light_icon_style_inactive

The `css` parameters are analogous to the ``icons`` - they are styles that are expected to be maipulated as part of the Widget's operation.
They will be made available to the widget at initialization time, and are mapped through the skin.

In the case of the light Base Widget they remain the same, but inb a scene for instance,
the touch pad is grey except when it is activated when it changes to green -
these styles are made available to the Base Widget to use for changing th style when the button is pressed.

Static CSS
~~~~~~~~~~

.. code:: yaml

    css:
    static_css:
      title_style: $light_title_style
      title2_style: $light_title2_style
      state_text_style: $light_state_text_style
      level_style: $light_level_style
      unit_style: $light_unit_style
      level_up_style: $light_level_up_style
      level_down_style: $light_level_down_style
      widget_style: $light_widget_style


The ``statis_css`` entry is used for styles that are automatically applied to various fields.
As with ``static_icons``, these are expected to be static and are automatically applied when the widget initializes.
Again, the variables are derived from the skin, and refer top things like titles that remain static for the lifetime of the widget.


Empty Values
~~~~~~~~~~~~

None of the special sections ``icons``, ``static_icons``, ``css``, ``static_css`` can be empty.
If no values are required, simply use the yaml syntax for an empty list - ``[]``. e.g.:

.. code:: yaml

    static_icons: []

Summary
~~~~~~~

In summary, a Derived Widget has 2 main functions:

#. Map values from the Instantiated Widget to the Base Widget, supplying hard coded parameters where necessary
#. Interact with the skin in use to provide the correct styles and icons to the Base Widget

It is technically possible to load a Base Widget into a dashboard directly but this is discouraged
as it bypasses the skinning.
For this reason, even if a Base Widget is used for a single type of widget, a Derived Widget is also required.

Base Widgets
------------

Base Widgets are where all the work actually gets done. To build a Base Widget you will need an
understanding of HTML and CSS as well as proficiency in JavaScript programming. Base Widgets are really just small
collections of HTML code, with associated CSS to control their appearance, and JavaScript to react to touches, and
update values based on state changes.

To build a new Base Widget, first create a directory in the appropriate place, named for the widget.
By convention, the name of the widget should start with ``base`` - this is to avoid confusion in the
dashboard creation logic between derived and base widgets. The directory will contain 3 files,
also named for the widget:

.. code:: bash

    hass@Pegasus:/export/hass/src/appdaemon/appdaemon/widgets/baselight$ ls -l
    total 16
    -rw-rw-r-- 1 hass hass 1312 Mar 19 13:55 baselight.css
    -rw-rw-r-- 1 hass hass  809 Mar 19 13:55 baselight.html
    -rw-rw-r-- 1 hass hass 6056 Apr 16 10:07 baselight.js
    hass@Pegasus:/export/hass/src/appdaemon/appdaemon/widgets/baselight$

The files are:

#. An HTML file that describes the various elements that the widget has, such as titles, value fields etc.
   The HTML file also defines data bindings that the JavaScript piece uses.
#. A CSS File - this describes the basic styles for the widget and is used for placement of elements too
#. A JavaScript file - this file uses the Widget API and contains all of the logic for the widget.

For the pusposes of this document we will provide examples from the ``baselight`` Base Widget.

Widget HTML Files
~~~~~~~~~~~~~~~~~




`Knockout <http://knockoutjs.com/index.html>`__

.. code:: html

    <h1 class="title" data-bind="text: title, attr:{style: title_style}"></h1>
    <h1 class="title2" data-bind="text: title2, attr:{style: title2_style}"></h1>
    <h2 class="icon" data-bind="attr:{style: icon_style}"><i data-bind="attr: {class: icon}"></i></h2>
    <span class="toggle-area" id="switch"></span>
    <p class="state_text" data-bind="text: state_text, attr:{style: state_text_style}"></p>
    <div class="levelunit">
    <p class="level" data-bind="text: level, attr:{style: level_style}"></p>
    <p class="unit" data-bind="html: units, attr:{style: unit_style}"></p>
    </div>
    <p class="secondary-icon minus"><i data-bind="attr: {class: icon_down, style: level_down_style}" id="level-down"></i></p>
    <p class="secondary-icon plus"><i data-bind="attr: {class: icon_up, style: level_up_style}" id="level-up"></i></p>



Widget CSS Files
~~~~~~~~~~~~~~~~


.. code:: css

    .widget-baselight-{{id}} {
        position: relative;
    }

    .widget-baselight-{{id}} .state_text {
        font-size: 85%;
    }

    .widget-baselight-{{id}} .title {
        position: absolute;
        top: 5px;
        width: 100%;
    }

    .widget-baselight-{{id}} .title2 {
        position: absolute;
        top: 23px;
        width: 100%;
    }

    .widget-baselight-{{id}} .state_text {
        position: absolute;
        top: 38px;
        width: 100%;
    }

    .widget-baselight-{{id}} .icon {
        position: absolute;
        top: 43px;
        width: 100%;
    }

    .widget-baselight-{{id}} .toggle-area {
        z-index: 10;
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 75%;
    }

    .widget-baselight-{{id}} .level {
        display: inline-block;
    }

    .widget-baselight-{{id}} .unit {
        display: inline-block;
    }

    .widget-baselight-{{id}} .levelunit {
        position: absolute;
        bottom: 5px;
        width: 100%;
    }

    .widget-baselight-{{id}} .secondary-icon {
        position: absolute;
        bottom: 0px;
        font-size: 20px;
        width: 32px;
        color: white;
    }

    .widget-baselight-{{id}} .secondary-icon.plus {
        right: 24px;
    }

    .widget-baselight-{{id}} .secondary-icon.plus i {
        padding-top: 10px;
        padding-left: 30px;
    }

    .widget-baselight-{{id}} .secondary-icon.minus {
        left: 8px;
    }

    .widget-baselight-{{id}} .secondary-icon.minus i {
        padding-top: 10px;
        padding-right: 30px;
    }


Widget JavaScript Files
~~~~~~~~~~~~~~~~~~~~~~~


.. code:: javascript

    function baselight(widget_id, url, skin, parameters)
    {
        // Will be using "self" throughout for the various flavors of "this"
        // so for consistency ...

        self = this

        // Initialization

        self.widget_id = widget_id

        // Parameters may come in useful later on

        self.parameters = parameters

        // Parameter handling

        if ("monitored_entity" in self.parameters)
        {
            entity = self.parameters.monitored_entity
        }
        else
        {
            entity = self.parameters.entity
        }

        if ("on_brightness" in self.parameters)
        {
            self.on_brightness = self.parameters.on_brightness
        }
        else
        {
            self.on_brightness = 127
        }

        // Define callbacks for on click events
        // They are defined as functions below and can be any name as long as the
        // 'self'variables match the callbacks array below
        // We need to add them into the object for later reference

        self.OnButtonClick = OnButtonClick
        self.OnRaiseLevelClick = OnRaiseLevelClick
        self.OnLowerLevelClick = OnLowerLevelClick

        var callbacks =
            [
                {"selector": '#' + widget_id + ' > span', "callback": self.OnButtonClick},
                {"selector": '#' + widget_id + ' #level-up', "callback": self.OnRaiseLevelClick},
                {"selector": '#' + widget_id + ' #level-down', "callback": self.OnLowerLevelClick},
            ]

        // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
        // Initial will be called when the dashboard loads and state has been gathered for the entity
        // Update will be called every time an update occurs for that entity

        self.OnStateAvailable = OnStateAvailable
        self.OnStateUpdate = OnStateUpdate

        var monitored_entities =
            [
                {"entity": entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
            ]

        // Finally, call the parent constructor to get things moving

        WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

        // Function Definitions

        // The StateAvailable function will be called when
        // self.state[<entity>] has valid information for the requested entity
        // state is the initial state

        function OnStateAvailable(self, state)
        {
            self.state = state.state;
            if ("brightness" in state.attributes)
            {
                self.level = state.attributes.brightness
            }
            else
            {
                self.level = 0
            }
            set_view(self, self.state, self.level)
        }

        // The OnStateUpdate function will be called when the specific entity
        // receives a state update - it's new values will be available
        // in self.state[<entity>] and returned in the state parameter

        function OnStateUpdate(self, state)
        {
            self.state = state.state;
            if ("brightness" in state.attributes)
            {
                self.level = state.attributes.brightness
            }
            else
            {
                self.level = 0
            }

            set_view(self, self.state, self.level)
        }

        function OnButtonClick(self)
        {
            if (self.state == "off")
            {
                args = self.parameters.post_service_active
                if ("on_attributes" in self.parameters)
                {
                    for (var attr in self.parameters.on_attributes)
                    {
                        args[attr] = self.parameters.on_attributes[attr]
                    }
                }
            }
            else
            {
                args = self.parameters.post_service_inactive
            }
            console.log(args)
            self.call_service(self, args)
            toggle(self)
        }

        function OnRaiseLevelClick(self)
        {
            self.level = self.level + 255/10;
            self.level = parseInt(self.level)
            if (self.level > 255)
            {
                self.level = 255
            }
            args = self.parameters.post_service_active
            args["brightness"] = self.level
            self.call_service(self, args)
        }

        function OnLowerLevelClick(self)
        {
            self.level = self.level - 255/10;
            if (self.level < 0)
            {
                self.level = 0;
            }
            self.level = parseInt(self.level)
            if (self.level == 0)
            {
                args = self.parameters.post_service_inactive
            }
            else
            {
                args = self.parameters.post_service_active
                args["brightness"] = self.level
            }
            self.call_service(self, args)
        }

        function toggle(self)
        {
            if (self.state == "on")
            {
                self.state = "off";
                self.level = 0
            }
            else
            {
                self.state = "on";
            }
            set_view(self, self.state, self.level)
        }

        // Set view is a helper function to set all aspects of the widget to its
        // current state - it is called by widget code when an update occurs
        // or some other event that requires a an update of the view

        function set_view(self, state, level)
        {

            if (state == "on")
            {
                // Set Icon will set the style correctly for an icon
                self.set_icon(self, "icon", self.icons.icon_on)
                // Set view will set the view for the appropriate field
                self.set_field(self, "icon_style", self.css.icon_style_active)
            }
            else
            {
                self.set_icon(self, "icon", self.icons.icon_off)
                self.set_field(self, "icon_style", self.css.icon_style_inactive)
            }
            if (typeof level == 'undefined')
            {
                self.set_field(self, "level", 0)
            }
            else
            {
                self.set_field(self, "level", Math.ceil((level*100/255) / 10) * 10)
            }
        }
    }


A Note on Skinning
------------------

As you have seen, when creating a new wiget, it is also necessary to add entries for the skinning variables.
When contributing widgets back, please ensure that you have provided entries for all of the included skins
that are sympathetic to the original look and feel, or the PR will not be accepted.




