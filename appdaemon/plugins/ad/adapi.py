import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon


class Ad(adbase.ADBase, adapi.ADAPI):

    # entities = Entities()

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars):

        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logging, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logging, args, config, app_config, global_vars)

    def listen_stream(self, subscribe_type, subscription, **kwargs):
        """Subscribes to a Stream on the Remote AD instance.
        This helper function used for subscribing to a stream on a remote AD instance,
        from within an AppDaemon App.
        This allows the apps to now access events from that stream, in realtime.
        So outside the initial configuration at plugin config, this allows access
        to other events while the apps runs. It should be noted that if AppDaemon
        was to reload, the events subscribed via this function will not be available
        by default. On those declared at the plugin config will always be available.
        It uses configuration specified in the plugin configuration which simplifies
        the call within the app significantly.
        Different AD instances can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.
        Args:
            subscribe_type (str): The type of stream to be subscribed to on the remote AD instance. This can be ``state`` or ``event``
            subscriptions (dict): This is a dictionary argument, that are to be subscribed to. The dictionary should contain the required data
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            None.

        Examples:
            >>> self.stream_subscribe("state", {"namespace" : "admin", "entity_id" : "Total Callbacks Fired"}, namespace = "ad)
        """

        if "type" not in kwargs:
            kwargs["type"] = subscribe_type

        if "subscription" not in kwargs:
            kwargs["subscription"] = subscription

        return self.call_service("stream/subscribe", **kwargs)

    def cancel_listen_stream(self, unsubscribe_type, handle, **kwargs):
        """Unsubscribes to a Stream on the Remote AD instance.
        This helper function used for unsubscribing to a stream on a remote AD instance,
        from within an AppDaemon App.
        This allows the apps to no longer access events from that stream, in realtime.
        So outside the initial configuration at plugin config, this allows to deny access
        to other events while the apps runs. It should be noted that if AppDaemon
        was to reload, the events subscribed via this function will be available
        by default. On those undeclared at the plugin config will not be available.
        Different AD instances can be accessed within an app, as long as they are
        all declared when the plugins are configured, and using the ``namespace``
        parameter.
        Args:
            unsubscribe_type (str): The type of stream to be unsubscribed to on the remote AD instance. This can be ``state`` or ``event``
            handle (str): This is the handle of the stream that is to be unsubscribed from
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            namespace (str, optional): Namespace to use for the call. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            None.

        Examples:
            >>> self.stream_subscribe("state", handle, namespace = "ad")
        """

        if "type" not in kwargs:
            kwargs["type"] = unsubscribe_type

        if "handle" not in kwargs:
            kwargs["handle"] = handle

        return self.call_service("stream/unsubscribe", **kwargs)
