import yaml
import asyncio
import copy

from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase


class DummyPlugin(PluginBase):
    def __init__(self, ad: AppDaemon, name, args):
        super().__init__(ad, name, args)

        self.AD = ad
        self.stopping = False
        self.config = args
        self.name = name

        self.logger.info("Dummy Plugin Initializing", "DUMMY")

        self.name = name

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "default"

        with open(args["configuration"], "r") as yamlfd:
            config_file_contents = yamlfd.read()
        try:
            self.config = yaml.load(config_file_contents, Loader=yaml.SafeLoader)
        except yaml.YAMLError as exc:
            self.logger.warning("Error loading configuration")
            if hasattr(exc, "problem_mark"):
                if exc.context is not None:
                    self.logger.warning("parser says")
                    self.logger.warning(str(exc.problem_mark))
                    self.logger.warning(str(exc.problem) + " " + str(exc.context))
                else:
                    self.logger.warning("parser says")
                    self.logger.warning(str(exc.problem_mark))
                    self.logger.warning(str(exc.problem))

        self.state = self.config["initial_state"]
        self.current_event = 0

        self.logger.info("Dummy Plugin initialization complete")

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)
        self.stopping = True

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []

    #
    # Get initial state
    #

    async def get_complete_state(self):
        self.logger.debug("*** Sending Complete State: {} ***".format(self.state))
        return copy.deepcopy(self.state)

    async def get_metadata(self):
        return {
            "latitude": 41,
            "longitude": -73,
            "elevation": 0,
            "time_zone": "America/New_York",
        }

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        pass
        # self.logger.debug("*** Utility ***".format(self.state))

    #
    # Handle state updates
    #

    async def get_updates(self):
        await self.AD.plugins.notify_plugin_started(
            self.name,
            self.namespace,
            self.get_metadata(),
            self.get_complete_state(),
            True,
        )
        while not self.stopping:

            if self.current_event >= len(self.config["sequence"]["events"]) and (
                "loop" in self.config["sequence"] and self.config["loop"] == 0 or "loop" not in self.config["sequence"]
            ):
                while not self.stopping:
                    await asyncio.sleep(1)
                return None
            else:
                event = self.config["sequence"]["events"][self.current_event]
                await asyncio.sleep(event["offset"])
                if "state" in event:
                    entity = event["state"]["entity"]
                    old_state = self.state[entity]
                    new_state = event["state"]["newstate"]
                    self.state[entity] = new_state
                    ret = {
                        "event_type": "state_changed",
                        "data": {"entity_id": entity, "new_state": new_state, "old_state": old_state},
                    }
                    self.logger.debug("*** State Update: %s ***", ret)
                    await self.AD.state.process_event(self.namespace, copy.deepcopy(ret))
                elif "event" in event:
                    ret = {
                        "event_type": event["event"]["event_type"],
                        "data": event["event"]["data"],
                    }
                    self.logger.debug("*** Event: %s ***", ret)
                    await self.AD.state.process_event(self.namespace, copy.deepcopy(ret))

                elif "disconnect" in event:
                    self.logger.debug("*** Disconnected ***")
                    self.AD.plugins.notify_plugin_stopped(self.namespace)

                elif "connect" in event:
                    self.logger.debug("*** Connected ***")
                    await self.AD.plugins.notify_plugin_started(self.namespace)

                self.current_event += 1
                if (
                    self.current_event >= len(self.config["sequence"]["events"])
                    and "loop" in self.config["sequence"]
                    and self.config["sequence"]["loop"] == 1
                ):
                    self.current_event = 0

    #
    # Set State
    #

    def set_plugin_state(self, entity, state, **kwargs):
        self.logger.debug("*** Setting State: %s = %s ***", entity, state)
        self.state[entity] = state

    def get_namespace(self):
        return self.namespace
