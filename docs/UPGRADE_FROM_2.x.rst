Upgrading from 2.x
==================

This documentation is for AppDaemon is 3.0.0 or later. If you are upgrading from a 2.x version, there have been some changes to the way AppDaemon is configured, and you will need to edit your config files and make some other changes. The changes are listed below:

Note that not all changes will apply to everyone, some of them are in fairly obscure parts of AppDaemon that few if any people use, however, everyone will have to make some changes, so read carefully.

- AppDaemon no longer supports python 3.4

This is a fairly significant step, and the decision to do this was influenced by HASS' pending end of support for Python 3.4. There are many technical reasons why this is a good thing, but the bottom line is that you will need to upgrade your python version to run HASS anyway, so I took this opportunity to follow suit. AppDaemon 3.0 will remain in beta until HASS drops python 3.4 support entirely.

- Apps need to change the import and super class

The naming and placement of the imports needed to change to support the plugin architecture, and to make more sense of the naming in a multiple plugin environment. You will need to edit each of your apps and change the top couple of lines from:

.. code:: python

   import appdaemon.appapi as appapi

   class MyClass(appapi.AppDaemon):
   ...


to:

.. code:: python

   import hassapi as hass

   class MyClass(hass.Hass):
   ...


Note, we are changing both the import name, and the superclass.

- ``info_listen_state()`` now returns the namespace in addition to the previous parameters

I introduced namespaces as a way of handling multiple plugins at the same time - the docs have more details, but if you are just using a single HASS instance, as everyone has been doing until now, you can safely ignore namespaces.

- The "ha_started" event has been renamed to "plugin_started"

If you use this event, the name has been changed. The plugin started event has a parameter called ``name`` which gives the name of the plugin that was restarted.

- RSS Feed parameters have been moved to the hadashboard section

When HADashboard is integrated with HASS, the config for HADashboard needs to be all in one place.

e.g.:

.. code:: yaml

   hadashboard:
     dash_url: http://192.168.1.20:5050
     rss_feeds:
       - feed: http://rss.cnn.com/rss/cnn_topstories.rss
         target: news
     rss_update: 300


- Log directives now have their own section

Logging is a function of the underlying execution code, not specifically AppDaemon (for instance, when integrated with HASS, AppDaemon will use HASS logging. For that Reason, the log directives were pulled out into their own section. The section is optional, and if not specified all the previous defaults will apply.

For example:

.. code:: yaml

   log:
     accessfile: /export/hass/appdaemon_test/logs/access.log
     errorfile: /export/hass/appdaemon_test/logs/error.log
     logfile: /export/hass/appdaemon_test/logs/appdaemon.log
     log_generations: 5
     log_size: 1024
   appdaemon:
   ...


- ``AppDaemon`` section renamed to ``appdaemon``, ``HADashboard`` section renamed to ``hadashboard``

This was done mainly for consistency, and because the capitals bugged me ;)

- Plugins (such as the HASS plugin now have their own parameters under the plugin section of the config file

This comes down to a reorganization of the appdaemon.yaml file to reflect the fact that there are now plugins and there may be more than one of them. Rather than having its own section, the HASS plugin is now listed under the ``appdaemon`` section, although the arguments remain the same. Here is an example:

.. code:: yaml

   appdaemon:
     api_port: 5001
     api_key: !secret appdaemon_key
     threads: 10
     time_zone: GMT+0BST-1,M3.5.0
     plugins:
       HASS:
         type: hass
         ha_key: !secret home_assistant_key
         ha_url: http://192.168.1.20:8123
         #commtype: SSE


- --commtype command line argument has been moved to the appdaemon.cfg file

This parameter applies specifically to HASS, so it made no sense to have it as a commandline argument. See above for an example.

- Accessing other Apps arguments is now via the ``app_config`` attribute, ``config`` retains just the AppDaemon configuration parameters

Required due to the restructuring of the config files.

- the self.ha_config attribute has been replaced by the ``self.get_hass_config()`` api call and now supports namespaces.

This reflects the fact that the yaml files have been reconfigured, and that the config info is now owned by the individual plugins.

- The !secret directive has been moved to the top level of appdaemon.yaml

The same argument as the logs - not strictly relevant to AppDaemon, more a concern of the execution environment.

- apps.yaml in the config directory has now been deprecated

One of the new features in 3.0 is that it is now possible to split the apps.yaml into multiple files. You are free to do this in any way you want and place the yaml files with any name, anywhere in the directory hierarchy under the appdir. Apart from flexibility, another reason for this was to prepare the way for later features around configuration tools and automatic app installs. For now, the only necessary step is to move your apps.yaml file from the config directory into the apps directory. If you do not, you will get a warning but everything should still work for now. If you do stick with apps.yaml at in the config directory for now, any other yaml files in the apps directory will be ignored.

- select_value() has been renamed to set_value() to harmonize with HASS

A minor change just to reflect the recent changes to HASS in this area, e.g ``input_slider`` being renamed to ``input_number`` and the service name changing.

- It is no longer possible to automatically migrate from the legacy cfg style of config, and support for cfg files has been dropped.

This has been on the cards for a while - if you are still using cfg files, use the latest 2.0 version of appdaemon to migrate to yaml style configuration before you upgrade to 3.0.

- App modules not listed in an apps.yaml file will no longer be loaded. Python modules may still be imported directly if they are in a directory in which other apps reside.

- ``cert_path`` is deprecated. With the replacement of requests with aiohttp, it is now sufficient to set ``cert_verify`` to False to use a self signed certificate.

- In apps.yaml, dependencies should now be a proper yaml list rather than a comma separated string

This rewrite introduces some breaking changes as dependencies are now tracked at the app level rather than the module level. This gives a lot more flexibility, and solves a couple of problems. For instance, @ReneTode, the undisputed AppDaemon power user has one App that he is running 60 different instances of. Under the old system, a change to one of those instances parameters in apps.yaml forced all 60 apps to reload - not good :) With the new app level dependencies, just the affected app will reload, along with any other apps that depend on it.

While I was in the code I made another change that I had been wanting to for a while - dependencies used to be a comma separated list, now they are a true yaml list.

So what does that mean for anyone upgrading? Well, if you weren't using dependencies before, then absolutely nothing, all should work the same.

If you were using dependencies, you will need to make some minor changes, to reference apps rather than modules, and to change the format for multiple entries. Here's an example of an old style dependency tree:

.. code:: yaml

   app1:
     module: module1
     class: class1
   app2:
     module: module2
     class: class2
   app3:
     module: module3
     class: class3
     dependencies: module1
   app4:
     module: module4
     class: class4
     dependencies: module1,module2


Under the new system we change the dependencies to apps and change the way the dependencies are listed:

.. code:: yaml

   app1:
     module: module1
     class: class1
   app2:
     module: module2
     class: class2
   app3:
     module: module3
     class: class3
     dependencies: app1
   app4:
     module: module4
     class: class4
     dependencies:
       - app1
       - app2

As you can see, single dependencies can be listed inline, but if you have more than one you must us the YAML list format.

For those of you that are relying on the module based reloading to force reloads of modules that aren't apps, this can be achieved using global module dependencies.
