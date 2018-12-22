import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils

class Mqtt(adbase.ADBase, adapi.ADAPI):

    def __init__(self, ad: AppDaemon, name, logging, args, config, app_config, global_vars,):

        # Call Super Classes
        adbase.ADBase.__init__(self, ad, name, logging, args, config, app_config, global_vars)
        adapi.ADAPI.__init__(self, ad, name, logging, args, config, app_config, global_vars)


    #
    # Override listen_state()
    #

    def listen_event(self, cb, event=None, **kwargs):
        namespace = self._get_namespace(**kwargs)

        if 'wildcard' in kwargs:
            wildcard = kwargs['wildcard']
            if wildcard[-2:] == '/#' and len(wildcard.split('/')[0]) >= 1:
                plugin = utils.run_coroutine_threadsafe(self, self.AD.plugins.get_plugin_object(namespace))
                utils.run_coroutine_threadsafe(self, plugin.process_mqtt_wildcard(kwargs['wildcard']))
            else:
                self.logger.warning("Using %s as MQTT Wildcard for Event is not valid, use another. Listen Event will not be registered", wildcard)
                return

        return super(Mqtt, self).listen_event(cb, event, **kwargs)

    #
    # service calls
    #
    def mqtt_publish(self, topic, payload = None, **kwargs):
        kwargs['topic'] = topic
        kwargs['payload'] = payload
        service = 'mqtt/publish'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_subscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'mqtt/subscribe'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_unsubscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'mqtt/unsubscribe'
        result = self.call_service(service, **kwargs)
        return result
