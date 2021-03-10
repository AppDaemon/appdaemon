Upgrading from 3.x
==================

This documentation is for AppDaemon is 4.0.0 or later. If you are upgrading from a 3.x version, there have been some changes to the way AppDaemon is configured, and you will need to edit your config files and make some other changes. The changes are listed below:

Note that not all changes will apply to everyone, some of them are in fairly obscure parts of AppDaemon that few if any people use, however, everyone will have to make some changes, so read carefully.

- ``log`` section is deprecated in favor of a new and more versatile ``logs`` section. In AppDaemon 4.x, each log can be configured individually for filename, maximum size, etc. and in addition, it now supports custom formats and additional user logs.

For more detail see the ``Log Configuration`` section in the Configuration section.

- ``api_port`` is no longer supported by the ``appdaemon`` section, it has moved to the new ``http`` component, and is defined by the port number in the ``url`` parameter. API Paths to apps have not changed. The App API, Dashboards and new Admin interface all share a single port, configured in the `http` section. For further details, see ``Configuring the HTTP Component`` in the Configuration section. To turn on support for the App Api, you will need to include an ``api`` section in AppDaemon.yaml - see the ``Configuring the API`` section in the Configuration section/

- ``latitude``, ``longitude``, ``elevation`` and ``timezone`` are now mandatory and are specified in the ``appdaemon`` section of appdaemon.yaml.
