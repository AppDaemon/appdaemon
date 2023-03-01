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
For example, in Home Assistant, a light and a group are fairly similar and require identical controls and status displays.
This makes it possible to create a single Base Widget and map to it with two separate Derived Widgets.
When creating a new Widget type, attempt to do one of the following in order of preference:

#. Create a new Derived Widget that works with an existing Base Widget
#. Create a new Derived Widget that works with modifications to an existing Base Widget
#. Create a new Derived and Base Widget

We also talk about a third type of widgets, an ``Instantiated Widget`` -
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
(``appdaemon/widgets``) then a Pull Request may be issued in the usual way.

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
(listed in the following sections) but any values are allowed and are all passed to the Base Widget.
The exception to this is the ``widget_type`` entry, which is required and refers to the Base Widget that this Derived
Widget works with.

In the example above, ``entity`` is an argument that will be made available to the base widget.
The value, ``{{entity}}`` is a simple passthrough from the Instantiated Widget in the Dashboard.
The significance of this is that a Derived Widget may want to hard code specific parameters while passing others through.
For example, a Base Widget may require a ``service`` parameter for which service to call to turn a device on.
A ``switch`` Derived Widget may hard code this as ``switch.turn_on`` while a ``light`` derived widget may hard code it
as ``light.turn_on``. Both however require the entity name from the Instantiated widget.
In practice, this example is somewhat artificial as you could use ``home_assistant.turn_on`` for both service calls,
and in fact, lights and switches have different Base Widgets, but the concept remains valid.

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

The `css` parameters are analogous to the ``icons`` - they are styles that are expected to be manipulated as part of the Widget's operation.
They will be made available to the widget at initialization time, and are mapped through the skin.

In the case of the light Base Widget they remain the same, but in a scene, for instance,
the touch pad is grey except when it is activated when it changes to green -
these styles are made available to the Base Widget to use for changing the style when the button is pressed.

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


The ``static_css`` entry is used for styles that are automatically applied to various fields.
As with ``static_icons``, these are expected to be static and are automatically applied when the widget initializes.
Again, the variables are derived from the skin, and refer to things like titles that remain static for the lifetime of the widget.


Empty Values
~~~~~~~~~~~~

None of the special sections ``icons``, ``static_icons``, ``css``, ``static_css`` can be empty.
If no values are required, simply use the yaml syntax for an empty list - ``[]``. e.g.:

.. code:: yaml

    static_icons: []

Summary
~~~~~~~

In summary, a Derived Widget has 2 main functions:

#. Map values from the Instantiated Widget to the Base Widget, supplying hard-coded parameters where necessary
#. Interact with the skin in use to provide the correct styles and icons to the Base Widget

It is technically possible to load a Base Widget into a dashboard directly but this is discouraged
as it bypasses the skinning.
For this reason, even if a Base Widget is used for a single type of widget, a Derived Widget is also required.

Base Widgets
------------

Base Widgets are where all the work actually gets done. To build a Base Widget you will need an
understanding of HTML and CSS as well as proficiency in JavaScript programming. Base Widgets are really just small
snippets of HTML code, with associated CSS to control their appearance, and JavaScript to react to touches, and
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

#. An HTML file that describes the various elements that the widget has, such as titles, value fields, etc.
   The HTML file also defines data bindings that the JavaScript piece uses.
#. A CSS File - this describes the basic styles for the widget and is used for placement of elements too
#. A JavaScript file - this file uses the Widget API and contains all of the logic for the widget.

For the purposes of this document, we will provide examples from the ``baselight`` Base Widget.

Widget HTML Files
~~~~~~~~~~~~~~~~~

The HTML files exist to provide a basic layout for the widget and insert the styles. They are usually fairly simple.

By convention, the various tag types have styling suitable for some common elements although that can be overidden in
the css file or the skin:

- <h1> is styled for small text such as titles or state text
- <h2> is styled for large icons or text values
- <p> is styled for small unit labels, e.g. ``%``

To assist with programmatically changing values and styles in the HTML, HADashboard uses `Knockout <http://knockoutjs.com/index.html>`__
From their web page:

    Knockout is a JavaScript library that helps you to create rich, responsive display and editor user interfaces with a clean underlying data model. Any time you have sections of UI that update dynamically (e.g., changing depending on the user’s actions or when an external data source changes), KO can help you implement it more simply and maintainable.

Knockout bindings are used to set various attributes and the binding types in use are as follows:

- data bind - used for setting text values
- attr, type style - used for setting styles
- attr, type class - used for displaying icons

It is suggested that you familiarize yourself with the bindings in use.

Here is an example of an HTML file.

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

- The first 2 ``<h1>`` tags set up ``title1`` and ``title2`` using a data bind for the values and style attributes to allow the
  styles to be set. These styles map back to the various ``css`` and ``static_css`` supplied as arguments to the widget and
  their names must match
- The ``<h2>`` tag introduces a large icon, presumably of a lightbulb or something similar. Here, because of the way that icons work,
  we are using a class attribute in Knockout to directly set the class of the element which has the effect of forcing an icon to be displayed
- The ``<span>`` is set up to allow the user to toggle the widget on and off and is referred to later in the JavaScript
- The ``<div>`` here is used for grouping the level and unit labels for the light, along with the included ``<p>`` tags which introduce the actual elements
- The last 2 ``<p>`` elements are for the up and down icons.

Widget CSS Files
~~~~~~~~~~~~~~~~

CSS files in widgets are used primarily for positioning of elements since most of the styling occurs in the skins.
Since each widget must have a unique id, the ``{id}`` piece of each selector name will be substituted with a unique
id ensuring that even if there are multiple instances of the same widget they will all behave correctly.

Other than that, this is standard CSS used for laying out the various HTML elements appropriately.

Here is an example that works with the HTML above.

.. code::

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

The JavaScript file is responsible for glueing all the pieces together:

- Registering callbacks for events
- Registering callbacks for touches
- Updating the fields, icons, styles as necessary

Let's take a look at a typical JavaScript Widget - the Baselight Widget.

.. code:: javascript

    function baselight(widget_id, url, skin, parameters)
    {

All widgets are declared with an initial function named for the widget functions within the .js file
although they are technically objects.

This function is, in fact, the constructor and is initially called when the widget is first loaded.
It is handed a number of parameters:

- widget_id - Unique identifier of the widget
- url - the url used to invoke the widget
- the name of the skin in use
- the parameters supplied by the dashboard for this particular widget

Next we need to set up our ``self`` variable:

.. code:: javascript

        // Will be using "self" throughout for the various flavors of "this"
        // so for consistency ...

        self = this

For the uninitiated, JavaScript has a somewhat confused notion of scopes when using objects, as scopes can be inherited
from different places depending on the mechanism for calling into the code. In Widgets, various tricks have been used
to present a consistent view to the user which requires an initial declaration of the self variable. From then on,
all calls pass this variable between calls to ensure consistency. It is recommended that the convention of
declaring ``self = this`` at the top of the function then rigidly sticking to the use of ``self`` is adhered to,
to avoid confusion.

.. code:: javascript

        // Initialization

        self.widget_id = widget_id

        // Parameters may come in useful later on

        self.parameters = parameters

Here we are storing the parameters in case we need them later.

.. code:: javascript


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

Here we process the parameters and set up any variables we may need to refer to later on.

The next step is to set up the widget to respond to various events such as button clicks and state changes.

.. code:: javascript

        // Define callbacks for on click events
        // They are defined as functions below and can be any name as long as the
        // 'self'variables match the callbacks array below
        // We need to add them into the object for later reference

        self.OnButtonClick = OnButtonClick
        self.OnRaiseLevelClick = OnRaiseLevelClick
        self.OnLowerLevelClick = OnLowerLevelClick

        var callbacks =
            [
                {"selector": '#' + widget_id + ' > span', "action": "click", "callback": self.OnButtonClick},
                {"selector": '#' + widget_id + ' #level-up', "action": "click", "callback": self.OnRaiseLevelClick},
                {"selector": '#' + widget_id + ' #level-down', "action": "click", "callback": self.OnLowerLevelClick},
            ]


There could be occasions when it is desirable to register for an event, and get the whole event data.
This is possible by registering and passing "DOMEventData" and boolen `true`, so that dashboard is aware of the fact the entire
event data is required. Below is an example

.. code:: javascript

            // Define callbacks for some mouse events
            // They are defined as functions below and can be any name as long as the
            // 'self'variables match the callbacks array below
            // We need to add them into the object for later reference

            self.OnMouseEvent = OnMouseEvent

            var callbacks =
                [
                    {"selector": '#' + widget_id + ' > span', "action": ["mousedown", "mouseup"], "DOMEventData": true, "callback": self.OnMouseEvent}
                ]

Each widget has the opportunity to register itself for button clicks or touches, or any other event type such as ``change``.
This is done by filling out the callbacks array (which is later used to initialize them).
Here we are registering 3 callbacks.

Looking at ``OnButtonClick`` as an example:

- OnButtonClick is the name of a function we will be declaring later
- self.OnButtonClick is being used to add it to the object
- In Callbacks, we have an entry that connects a jQuery selector to that particular callback, such that
  when the element identified by the selector is clicked, the callback in the list will be called.
- ``action`` defines the jQuery action type the callback will respond to, e.g. ``click`` or ``change``

Once the widget is running, the OnButtonClick function will be called whenever the span in the HTML file is touched.
You may have noticed that in the CSS file we placed the span on top of everything else and made it cover the entire
widget.

Note that there is nothing special about the naming of ``OnButtonClick`` - it can be called anything as long as
the correct references are present in the ``callbacks`` list.

When subscribing to events that relate to value changes in a widget,
such as for instance an input select being changed by a user, which we must propagate back to Home Assistant,
there is an issue with race conditions if we subscribe to the normal `change` event. The `change` event will fire,
and our `onChange` function may be called before the knockout binding has an opportunity to update itself,
and we will see the old value. To handle this situation, a second type of event subscription is provided -
we will subscribe to the knockout binding changing rather than the control itself. This is done in a similar way
to the previous mechanism, the only difference is that instead of a `selector` parameter, we use an
`observable` parameter which is the name of the binding you want to subscribe to. For instance:


.. code:: javascript

        {"observable": "selectedoption", "action": "change", "callback": self.onChange}

Both styles of callback may be used together.

Next we will setup the state callbacks:

.. code:: javascript


        // Define callbacks for entities - this model allows a widget to monitor multiple entities if needed
        // Initial will be called when the dashboard loads and state has been gathered for the entity
        // Update will be called every time an update occurs for that entity

        self.OnStateAvailable = OnStateAvailable
        self.OnStateUpdate = OnStateUpdate

        var monitored_entities =
            [
                {"entity": entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate}
            ]

This is a similar concept to tracking state changes and displaying them. For the purposes of a widget,
we care about 2 separate things:

#. Getting an initial value for the state when the widget is first loaded
#. Tracking changes to the state over time

The first is accomplished by a callback when the widget is first loaded. We add a callback for the entity we are
interested in and identify which routine will be called initially when the widget is loaded, and which callback will be
called whenever we see a state update. These functions will be responsible for updating the fields necessary to show
initial state and changes over time. How that happens is a function of the widget design, but for instance, a
change to a sensor will usually result in that value being displayed in one of the HTML fields.

Here we are tracking just one entity, but it is possible to register callbacks on as many entities as you need for your
widget.

When that is in place we finalize the initialization:

.. code:: javascript

        // Finally, call the parent constructor to get things moving

        WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks)

After all the setup is complete, we need to make a call to the object's parent constructor to start processing, passing in
various parameters, some of which we got from the function call itself, and other like the callbacks that we
set up ourselves. The callback parameters must exist but can be empty, e.g. ``callbacks = []`` -
not every widget needs to respond to touches, not every widget needs to respond to state changes.

After this call completes, the initializer is complete and from now on, activity in the widget is governed by
callbacks either from initial state, state changes or button clicks,

Next, we will define our state callbacks:

.. code:: javascript

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

This function was one of the ones that we referred to earlier in the ``monitored_entities`` list. Since we identified
this as the ``initial`` callback, it will be called with an initial value for the entities state when the widget is
first loaded, but after the constructor function has completed. It is handed a self-reference, and the state for the
entity it subscribed to. What happens when this code is called is up to the widget. In the case of Base Light it will
set the icon type depending on whether the light is on or off, and also update the level.
Since this is done elsewhere in the widget, I added a function called ``set_view`` to set these things up.
There is also some logic here to account for the fact that in Home Assistant a light has no brightness level if it is
off, so ``0`` is assumed. Here, we also make a note of the current state for later reference - ``self.state = state.state``

- ``self.state`` is an object attribute
- ``state.state`` is the actual state of the entity. Like other Home Assistant state descriptions it can also have
  a set of sub-attributes under ``state.attributes`` for values like brightness or color etc.

``OnStateUpdate`` at least for this widget is very similar to ``OnStateAvailable``,
in fact it could probably be a single function for both ``initial`` and ``update`` but I separated it out for clarity.

.. code:: javascript

        // The OnStateUpdate function will be called when the specific entity
        // receives a state update - its new values will be available
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


Next, we define the functions that we referenced in the ``callback`` list for the various click actions. First,
``OnButtonClick`` is responding to someone touching the widget to toggle the state from off to on or vice-versa.

.. code:: javascript

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
            self.call_service(self, args)
            toggle(self)
        }

This is less complicated than it looks. What is happening here is that based on the current state of the entity,
we are selecting which service to call to change that state. We are looking it up in our parameters that we saved earlier.

So, if the light is ``off`` we consult our parameters for ``post_service_active`` which should be set to a service that
will turn the light on (e.g. ``light/turn_on``). Similarly, if it is on, we look for ``post_service_inactive`` to
find out how to turn it off. Once we have made that choice we make the service call to effect
the change: ``self.call_service()``

The additional logic and loop when state is off is to construct the necessary dictionary of additional parameters in
the format the ``turn_on`` service expects to set brightness, color, etc, that may be passed into the widget.

Usually, HADashboard understands ``args`` values as a single string. If you need to use a service that expects to
receive a list or a dictionary then you may use the special key ``json_args`` and set its value to a stringified
json. For example, suppose you want to pass to the service a list called ``colors``, then you could change the above
code and include another check:

.. code:: javascript

            if ("my_json" in self.parameters)
            {
               args["json_args"] =  JSON.stringify(self.parameters.my_json);
            }

The corresponding widget configuration may include something like this:

.. code:: yaml

    my_json:
       colors:
         - red
         - blue
         - green

Raise level is fairly explanatory - this is clicked to make the light brighter:

.. code:: javascript

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

Here we are using ``post_service_active`` and setting the brightness attribute. Each click will jump 10 units.
Lower level is very similar:

 .. code:: javascript

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

It is slightly more complex in that rather than setting the level to ``0``, when it gets there it turns the light off.

Finally, the toggle function is called by both of the above functions to change the stored state of the entity and
update the display (using ``set_view()`` again)

.. code:: javascript

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

Set_view() is where we attend to updating the widgets actual display based on the current state that may have just
changed.

.. code:: javascript


        // Set view is a helper function to set all aspects of the widget to its
        // current state - it is called by widget code when an update occurs
        // or some other event that requires an update of the view

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

The most important concept here are the 2 calls to update fields:

- set_icon() - update an icon to a different one, usually used to switch from an on representation to an off
  representation and vice-versa
- set_field() - update a field to show a new value. In this case the brightness field is being update
  to show the latest value

That is the anatomy of a typical widget - here it is in full:

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
        // receives a state update - its new values will be available
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
        // or some other event that requires an update of the view

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

As you have seen, when creating a new widget, it is also necessary to add entries for the skinning variables.
When contributing widgets back, please ensure that you have provided entries for all of the included skins
that are sympathetic to the original look and feel, or the PR will not be accepted.
