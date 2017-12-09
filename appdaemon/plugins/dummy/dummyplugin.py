import yaml
import asyncio
import copy

import appdaemon.utils as utils

class DummyPlugin:

    def __init__(self, ad, name, logger, error, loglevel,args):

        self.AD = ad
        self.logger = logger
        self.error = error
        self.stopping = False
        self.loglevel = loglevel
        self.config = args

        utils.log(self.logger, "INFO", "Dummy Plugin Initializing")

        self.name = name

        if "namespace" in args:
            self.namespace = args["namespace"]
        else:
            self.namespace = "dummy"

        if "verbose" in args:
            self.verbose = args["verbose"]
        else:
            self.verbose = False

        with open(args["configuration"], 'r') as yamlfd:
            config_file_contents = yamlfd.read()
        try:
            self.config = yaml.load(config_file_contents)
        except yaml.YAMLError as exc:
            utils.log(self.logger, "WARNING", "Error loading configuration")
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    utils.log(self.error, "WARNING", "parser says")
                    utils.log(self.error, "WARNING", str(exc.problem_mark))
                    utils.log(self.error, "WARNING", str(exc.problem) + " " + str(exc.context))
                else:
                    utils.log(self.error, "WARNING", "parser says")
                    utils.log(self.error, "WARNING", str(exc.problem_mark))
                    utils.log(self.error, "WARNING", str(exc.problem))

        self.state = self.config["initial_state"]
        self.current_event = 0

        utils.log(self.logger, "INFO", "Dummy Plugin initialization complete")

    def log(self, text):
        if self.verbose:
            utils.log(self.logger, "INFO", text)


    def stop(self):
        self.log("*** Stopping ***")
        self.stopping = True

    #
    # Get initial state
    #

    def get_complete_state(self):
        self.log("*** Sending Complete State: {} ***".format(self.state))
        return copy.deepcopy(self.state)

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        self.log("*** Utility ***".format(self.state))

    #
    # Handle state updates
    #

    async def get_updates(self):
        while not self.stopping:
            ret = None
            if self.current_event >= len(self.config["sequence"]["events"]) and ("loop" in self.config["sequence"] and self.config["loop"] == 0 or "loop" not in self.config["sequence"]):
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
                    ret = \
                        {
                            "event_type": "state_changed",
                            "data":
                                {
                                    "entity_id": entity,
                                    "new_state": new_state,
                                    "old_state": old_state
                                }
                        }
                elif "event" in event:
                    ret = \
                        {
                            "event_type": event["event"]["event_type"],
                            "data": event["event"]["data"],
                        }

                self.current_event += 1
                if self.current_event >= len(self.config["sequence"]["events"]) and "loop" in self.config["sequence"] and self.config["sequence"]["loop"] == 1:
                    self.current_event = 0
                self.log("*** State Update: {} ***".format(ret))
                self.AD.state_update(self.namespace, copy.deepcopy(ret))

    #
    # Set State
    #

    def set_state(self, entity, state):
        self.log("*** Setting State: {} = {} ***".format(entity, state))
        self.state[entity] = state

    def get_namespace(self):
        return self.namespace