import appdaemon.appapi as appapi
import appdaemon.utils as utils


class Entities:

    def __get__(self, instance, owner):
        state = utils.StateAttrs(instance.ad.get_state(instance.namespace, None, None, None))
        return state


class Mqtt(appapi.AppDaemon):

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars,):

        super(Mqtt, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        self.namespace = "mqtt"
        self.AD = ad
        self.name = name
        self._logger = logger
        self._error = error
        self.args = args
        self.config = config
        self.app_config = app_config
        self.global_vars = global_vars

    def set_namespace(self, namespace):
        self.namespace = namespace

    def _get_namespace(self, kwargs):
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]
            del kwargs["namespace"]
        else:
            namespace = self.namespace

        return namespace

    #
    # Listen state stub here as super class doesn't know the namespace
    #

    def listen_state(self, cb, entity=None, **kwargs):
        namespace = self._get_namespace(kwargs)
        return None

    def listen_event(self, cb, event=None, **kwargs):
        # namespace = self._get_namespace(**kwargs)
        # if "namespace" in kwargs:
        #     del kwargs["namespace"]
        return super(Mqtt, self).listen_event(self.namespace, cb, event, **kwargs)

    #
    # Likewise with get and set state
    #

    def get_state(self, entity=None, **kwargs):
        namespace = self._get_namespace(kwargs)
        return None

    def set_state(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        return None

    def entity_exists(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        return None

    def get_mqtt_config(self, **kwargs):
        print(self.namespace)
        return None
