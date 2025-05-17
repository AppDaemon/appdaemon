from typing import Any, Callable

from appdaemon.adapi import ADAPI
from appdaemon.adbase import ADBase


class Hass(ADBase, ADAPI):
    def call_service(
        self,
        service: str,
        namespace: str | None = None,
        timeout: str | int | float | None = None,
        callback: Callable | None = None,
        hass_timeout: str | int | float | None = None,
        suppress_log_messages: bool = False,
        **data,
    ) -> Any:
        """Calls a Service within AppDaemon.

        Services represent specific actions, and are generally registered by plugins or provided by AppDaemon itself.
        The app calls the service only by referencing the service with a string in the format ``<domain>/<service>``, so
        there is no direct coupling between apps and services. This allows any app to call any service, even ones from
        other plugins.

        Services often require additional parameters, such as ``entity_id``, which AppDaemon will pass to the service
        call as appropriate, if used when calling this function. This allows arbitrary data to be passed to the service
        calls.

        Apps can also register their own services using their ``self.regsiter_service`` method.

        Args:
            service (str): The service name in the format `<domain>/<service>`. For example, `light/turn_on`.
            namespace (str, optional): It's safe to ignore this parameter in most cases because the default namespace
                will be used. However, if a `namespace` is provided, the service call will be made in that namespace. If
                there's a plugin associated with that namespace, it will do the service call. If no namespace is given,
                AppDaemon will use the app's namespace, which can be set using the ``self.set_namespace`` method. See
                the section on `namespaces <APPGUIDE.html#namespaces>`__ for more information.
            timeout (str | int | float, optional): The internal AppDaemon timeout for the service call. If no value is
                specified, the default timeout is 60s. The default value can be changed using the
                ``appdaemon.internal_function_timeout`` config setting.
            callback (callable): The non-async callback to be executed when complete. It should accept a single
                argument, which will be the result of the service call. This is the recommended method for calling
                services which might take a long time to complete. This effectively bypasses the ``timeout`` argument
                because it only applies to this function, which will return immediately instead of waiting for the
                result if a `callback` is specified.
            hass_timeout (str | int | float, optional): Only applicable to the Hass plugin. Sets the amount of time to
                wait for a response from Home Assistant. If no value is specified, the default timeout is 10s. The
                default value can be changed using the ``ws_timeout`` setting the in the Hass plugin configuration in
                ``appdaemon.yaml``. Even if no data is returned from the service call, Home Assistant will still send an
                acknowledgement back to AppDaemon, which this timeout applies to. Note that this is separate from the
                ``timeout``. If ``timeout`` is shorter than this one, it will trigger before this one does.
            suppress_log_messages (bool, optional): Only applicable to the Hass plugin. If this is set to ``True``,
                Appdaemon will suppress logging of warnings for service calls to Home Assistant, specifically timeouts
                and non OK statuses. Use this flag and set it to ``True`` to supress these log messages if you are
                performing your own error checking as described `here <APPGUIDE.html#some-notes-on-service-calls>`__
            service_data (dict, optional): Used as an additional dictionary to pass arguments into the ``service_data``
                field of the JSON that goes to Home Assistant. This is useful if you have a dictionary that you want to
                pass in that has a key like ``target`` which is otherwise used for the ``target`` argument.
            **data: Any other keyword arguments get passed to the service call as ``service_data``. Each service takes
                different parameters, so this will vary from service to service. For example, most services require
                ``entity_id``. The parameters for each service can be found in the actions tab of developer tools in
                the Home Assistant web interface.

        Returns:
            Result of the `call_service` function if any, see
            `service call notes <APPGUIDE.html#some-notes-on-service-calls>`__ for more details.

        Examples:
            HASS
            ^^^^

            >>> self.call_service("light/turn_on", entity_id="light.office_lamp", color_name="red")
            >>> self.call_service("notify/notify", title="Hello", message="Hello World")
            >>> events = self.call_service(
                    "calendar/get_events",
                    entity_id="calendar.home",
                    start_date_time="2024-08-25 00:00:00",
                    end_date_time="2024-08-27 00:00:00",
                )["result"]["response"]["calendar.home"]["events"]

            MQTT
            ^^^^

            >>> self.call_service("mqtt/subscribe", topic="homeassistant/living_room/light", qos=2)
            >>> self.call_service("mqtt/publish", topic="homeassistant/living_room/light", payload="on")

            Utility
            ^^^^^^^

            It's important that the ``namespace`` arg is set to ``admin`` for these services, as they do not exist
            within the default namespace, and apps cannot exist in the ``admin`` namespace. If the namespace is not
            specified, calling the method will raise an exception.

            >>> self.call_service("app/restart", app="notify_app", namespace="admin")
            >>> self.call_service("app/stop", app="lights_app", namespace="admin")
            >>> self.call_service("app/reload", namespace="admin")

        """
        ...
