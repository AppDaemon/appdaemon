import asyncio

from appdaemon.appdaemon import AppDaemon


class AppQ:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.stopping = False

        #
        # Initial Setup
        #

        self.appq = asyncio.Queue(maxsize=0)

    def stop(self):
        self.stopping = True
        # Queue a fake event to make the loop wake up and exit
        self.appq.put_nowait({"namespace": "global", "event_type": "ad_stop", "data": None})

    async def loop(self):
        while not self.stopping:
            args = await self.appq.get()
            namespace = args["namespace"]
            await self.AD.state.state_update(namespace, args)
            self.appq.task_done()

    def fire_app_event(self, namespace, event):
        self.AD.logging.log("DEBUG", "fire_app_event: {}".format(event["event_type"]))
        event["namespace"] = namespace
        self.appq.put_nowait(event)

    def set_app_state(self, namespace, entity_id, state):
        self.AD.logging.log("DEBUG", "set_app_state: {}".format(entity_id))
        if entity_id is not None and "." in entity_id:
            if self.AD.state.entity_exists(namespace, entity_id):
                old_state = self.AD.state.get_entity(namespace, entity_id)
            else:
                old_state = None
            data = {"entity_id": entity_id, "new_state": state, "old_state": old_state}
            args = {"namespace": namespace, "event_type": "state_changed", "data": data}
            self.appq.put_nowait(args)
