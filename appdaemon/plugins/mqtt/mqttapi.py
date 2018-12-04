import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon

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
                self._AD.plugins.get_plugin_object(namespace).process_mqtt_wildcard(kwargs['wildcard'])
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
        service = 'publish'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_subscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'subscribe'
        result = self.call_service(service, **kwargs)
        return result

    def mqtt_unsubscribe(self, topic, **kwargs):
        kwargs['topic'] = topic
        service = 'unsubscribe'
        result = self.call_service(service, **kwargs)
        return result

    def call_service(self, service, **kwargs):
        self.logger.debug("call_service: %s, %s", service, kwargs)
        
        namespace = self._get_namespace(**kwargs)

        if 'topic' in kwargs:
            if not self._AD.plugins.get_plugin_object(namespace).initialized: #ensure mqtt plugin is connected
                self.logger.warning("Attempt to call Mqtt Service while disconnected: %s", service)
                return None

            try:
                result = self._AD.plugins.get_plugin_object(namespace).mqtt_service(service, **kwargs)
                
            except Exception as e:
                config = self._AD.plugins.get_plugin_object(namespace).config
                if config['type'] == 'mqtt':
                    self.logger.debug('Got the following Error %s, when trying to retrieve Mqtt Plugin' ,e)
                    return str(e)
                else:
                    self.logger.critical('Wrong Namespace %s selected for MQTT Service. Please use proper namespace before trying again', namespace)
                    return 'ERR'
        else:
            self.logger.warning('Topic not provided for Service Call {!r}.'.format(service))
            raise ValueError("Topic not provided, please provide Topic for Service Call")

        return result
