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
wheras Derived Widgets are just a structured list of variables that are passed down to Base Widgets.
Base Widgets live in subdirectories, Derived Widgets are simply yaml files.

The reason for the 2 types of widget is one of design philosophy. The goal is to have relatively few
Base Widgets, and multiple derived widgets that map to them with minor parameter changes.
For example, in Home Assistant, a light and a group are fairly similar, and require identical controls and status displays.
This makes it possible to create a single Base Widget, and map to it with two separate Derived Widgets.
When creating a new Widget type, attempt to do one of the following in order of preference:

#. Create a new Derived Widget that works with an existing Base Widget
#. Create a new Derived Widget that works with modifications to an existing Base Widget
#. Create a new Derived and Base Widget

We also talk abour a third type of widgets, an ``Instantiated Widget`` - this refers to an actual widget in a dashboard configuration file which will have a widget type and a number of specific variables.

Creating Custom Widgets
-----------------------

When creating new widgets, in a similar way to custom skins,
HADashboard allows the creation of a directory called ``custom_widgets`` in the configuration directory.
Any yaml files placed in here will be treated as new Base Widgets. Any directories here will be treated as new Base Widgets.
If you are creating a new widget you will need to use a new name for the widget. Base Widgets by convention are stored in directories
that are named starting with ``base`` e.g. ``baselight``, or ``basesuperwidget``.

If either a Derived Widget or Base Widget have the same name as an existing widget, the custom widget will be used in preference to allow
existing widgets to be easily modified.

When a widget has been created and tested, and the author desires to contribute the widget back to the community,
all that is required is that the Derived and Base Widgets are placed in the Git Repository in the standard widget directory (``appdaemon/widgets``)
then a Pull Request may be issued in the ususal way.

Derived Widgets
---------------

A derived widget is simply a ``yaml`` file with a number of known fields to describe the widget.
A secondary function of derived widgets is to map in CSS variables for sknning - more on that later

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

Any entries at the top level are simply variables to be passed to the Base Widget.
The exception to this is the ``widget_type`` entry, which is required and refers to the basewidghet that this Derived Widget works with.

In the example above, ``entity`` is an argument that will be made available to the base widget.
The value, ``{{entity}}`` is a simple passthrough from the Instantiated Widget in the Dashboard.
The significance of this is that a Derived Widget may want to hard code specific parameters while passing others through.
For example, a Base Widget may require a ``service`` parameter for which service to call to turn a device on.
A ``switch`` Derived Widget may hard code this as ``switch.turn_on`` while a ``light`` derived widget may hard code it as ``light.turn_on``.
Both however require the entity name from the Instantiated widget.
In practice, this example is somewhat artificial as you could use ``home_assistant.turn_on`` for both service calls, and in fact lights and switches have different Base Widgets, but the concept remains valid.

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

The icons parameter refers to icons that may be in use in ther Base Widget. The names must match what the Base Widget is expecting.
These Icons are expected to be manipulated by the Base Widget and are provided as specific arguments to it. Whilst it is possible to hard code these,
the intended use here is to use variables like the above. These variables map back to variables in the skin in use and are duplicated, possibly with different values in different skins.

The corresponding skin entries for these in the default skin are:

.. code:: yaml

    light_icon_on: fa-circle
    light_icon_off: fa-circle-thin

These could be different in another skin.

Static Icons
~~~~~~~~~~~~

.. code:: yaml

    static_icons:
      icon_up: $light_icon_up
      icon_down: $light_icon_down

Static icons are similar in concept to fields in that they map directly to fields in the widget and will be
prepopulated automatically under the assumption that they don't need to change.
As with the icons, the actual values are mapped in the skin.

CSS
~~~

.. code:: yaml

    css:
      icon_style_active: $light_icon_style_active
      icon_style_inactive: $light_icon_style_inactive

The `css` parameters are analogous to the ``icons`` - they are styles that are expected to be maipulated as part of the Widget's operation.
They will be made available to the widget at initialization time, and are mapped through the skin.

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
Again, the variables are derived from the skin.


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

It is technically possible to load a Base Widget into a dashboard directly but this is discouraged as it bypasses the skinning.
For this reason, even if a Base Widget is used for a single type of widget, a Derived Widget is also required.

Base Widgets
------------






