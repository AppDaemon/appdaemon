import appdaemon.appapi as appapi
import appdaemon.utils as utils


class Entities:

    def __get__(self, instance, owner):
        state = utils.StateAttrs(instance.ad.get_state(instance.namespace, None, None, None))
        return state


class Dummy(appapi.AppDaemon):

    entities = Entities()

    def __init__(self, ad, name, logger, error, args, config, app_config, global_vars,):

        super(Dummy, self).__init__(ad, name, logger, error, args, config, app_config, global_vars)

        self.namespace = "default"
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
        return super(Dummy, self).listen_state(namespace, cb, entity, **kwargs)

    #
    # Likewise with get and set state
    #

    def get_state(self, entity=None, **kwargs):
        namespace = self._get_namespace(kwargs)
        return super(Dummy, self).get_state(namespace, entity, **kwargs)

    def set_state(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        self._check_entity(namespace, entity_id)
        self.AD.log(
            "DEBUG",
            "set_state: {}, {}".format(entity_id, kwargs)
        )

        if entity_id in self.get_state():
            new_state = self.get_state()[entity_id]
        else:
            # Its a new state entry
            new_state = {}
            new_state["attributes"] = {}

        if "state" in kwargs:
            new_state["state"] = kwargs["state"]

        if "attributes" in kwargs:
            new_state["attributes"].update(kwargs["attributes"])

        # Send update to plugin

        self.AD.get_plugin(namespace).set_state(entity_id, new_state)

        # Update AppDaemon's copy

        self.AD.set_state(namespace, entity_id, new_state)

        return new_state

    def entity_exists(self, entity_id, **kwargs):
        namespace = self._get_namespace(kwargs)
        return self.AD.entity_exists(namespace, entity_id)

    def get_ha_config(self, **kwargs):
        print(self.namespace)
        return self.AD.get_plugin_meta(self.namespace)
