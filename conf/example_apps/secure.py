import hassapi as hass
import threading
import time
import random
import re

#
# App to manage check and action security
#
#
# Release Notes
#
# Version 1.0:
#   Initial Version


class Secure(hass.Hass):
    def initialize(self):
        self.action_lock = threading.RLock()
        for entity in self.list_entities():
            self.listen_state(self.state_event, entity)
        self.listen_event(self.security_event, "SECURE")
        if "alarm_entity" in self.args:
            self.listen_event(self.alarm_service, "call_service")
            self.listen_state(self.alarm_state, self.args["alarm_entity"])

    def alarm_service(self, event_name, data, kwargs):
        if data["domain"] == "alarm_control_panel" and data["service_data"]["entity_id"] == self.args["alarm_entity"]:
            if data["service"] == "alarm_arm_home" or data["service"] == "alarm_arm_away":
                insecure, message = self.query_house({"type": data["service"]})
                if insecure:
                    self.call_service(
                        "alarm_control_panel/alarm_disarm",
                        entity_id=self.args["alarm_entity"],
                        code=self.args["alarm_code"],
                    )

    def alarm_state(self, entity, attribute, old, new, kwargs):
        if old == "disarmed" and new == "pending":
            self.arming_alert()
        elif (old == "armed_home" or old == "armed_away") and new == "pending":
            self.triggered_alert()
        elif old == "pending" and (new == "armed_home" or new == "armed_away"):
            self.armed_alert()
        elif new == "disarmed":
            self.disarmed_alert()
        elif new == "triggered":
            self.alarm_alert()

    def state_event(self, entity, attribute, old, new, kwargs):
        # self.verbose_log("Monitored entity changed state: {}: {} -> {}".format(entity, old, new))
        armed = False
        zone_list = []

        if "alarm_entity" in self.args:
            state = self.get_state(self.args["alarm_entity"])
            # self.verbose_log("Alarm state is: {}".format(state))

            if state == "armed_home":
                zone_list = self.args["armed_home_zones"]
                armed = True
            elif state == "armed_away":
                zone_list = self.args["armed_away_zones"]
                armed = True

        if armed:
            entities = {key: value for (key, value) in self.filter_entities(zone_list)}
            if entity in entities and old == entities[entity]["desired_state"]:
                self.log("Alert - activating alarm!")
                self.call_service(
                    "alarm_control_panel/alarm_trigger",
                    entity_id=self.args["alarm_entity"],
                    code=self.args["alarm_code"],
                )
                # self.notify_alarm(entity, old, new)

    def security_event(self, event_name, data, kwargs):
        if data["type"] == "secure" or data["type"] == "query":
            self.query_house(data)

    def filter_entities(self, zonelist):
        for zone in self.args["zones"]:
            if zone in zonelist:
                for entity in self.args["zones"][zone]:
                    yield entity, self.args["zones"][zone][entity]

    def find_entity(self, id):
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                if entity == id:
                    return self.args["zones"][zone][entity]
        return None

    def list_entities(self):
        entities = []
        for zone in self.args["zones"]:
            for entity in self.args["zones"][zone]:
                entities.append(entity)
        return entities

    def query_house(self, data):  # noqa: C901

        self.timeout = 0
        secure_items = []
        insecure_items = []
        self.secured_items = []
        self.unsecured_items = []
        self.attempted_items = []

        self.data = data

        #
        # Pop up secure panel if configured
        #
        if "secure_panel" in self.args:
            if "secure_panel_timeout" in self.args:
                timeout = self.args["secure_panel_timeout"]
            else:
                timeout = 10

            self.dash_navigate(self.args["secure_panel"], timeout=timeout, ret="/MainPanel")

        zone_list = []
        if data["type"] == "query":
            zone_list = self.args["query_zones"]
        elif data["type"] == "secure":
            zone_list = self.args["secure_zones"]
        elif data["type"] == "alarm_arm_home":
            zone_list = self.args["armed_home_zones"]
        elif data["type"] == "alarm_arm_away":
            zone_list = self.args["armed_away_zones"]
        elif data["type"] == "alarm_disarm":
            # self.tts_log(self.get_message("alarm_disarm_message"), 0.5, 2)
            return False, ""

        # Figure out which items are secure vs insecure
        for id, values in self.filter_entities(zone_list):
            desired_state = values["desired_state"]
            state = self.get_state(id)
            if state != desired_state:
                insecure_items.append(id)
            else:
                secure_items.append(id)
        if not insecure_items:
            # All secure, tell the user
            message = self.report(False)

            if "caller" not in data:
                self.tts_log(message, self.args["announcement_volume"], 10)

            return False, message
        else:

            self.log("Checking items ...")
            for id in insecure_items:

                entity = self.find_entity(id)
                if "timeout" in entity and entity["timeout"] > self.timeout:
                    self.timeout = entity["timeout"]

                desired_state = entity["desired_state"]
                if "service" in entity and data["type"] == "secure":
                    service = entity["service"]
                    self.log("Calling {} -> {} on {}".format(service, desired_state, id))
                    self.attempted_items.append(id)
                    self.listen_state(self.state_change, id, new=desired_state)
                    self.call_service(service, entity_id=id)
                    self.secured_items.append(id)
                else:
                    self.unsecured_items.append(id)

            self.retry = 0
            # self.handle = self.run_every(self.check_actions, self.datetime(), 1)

            #
            # Wait until all actions complete or timeout occurs
            #
            complete = False
            while self.retry < self.timeout and not complete:
                time.sleep(1)
                with self.action_lock:
                    if not self.attempted_items:
                        complete = True
                self.retry += 1
                if "caller" in data and self.retry > 7:
                    # We are in danger of Alexa timing out so respond with what we have
                    message = self.report()
                    return True, message

            message = self.report()

            if "caller" not in data:
                self.tts_log(message, self.args["announcement_volume"], 10)

            return len(self.unsecured_items) != 0, message

    def state_change(self, entity, attribute, old, new, kwargs):
        with self.action_lock:
            if entity in self.attempted_items:
                self.attempted_items.remove(entity)

    def get_message(self, message_type):
        if message_type in self.data:
            messages = self.data[message_type]
        elif message_type in self.args:
            messages = self.args[message_type]
        else:
            messages = "Unknown message"

        if isinstance(messages, list):
            return random.choice(messages)
        else:
            return messages

    def report(self, all_secure=False):

        if all_secure:

            return self.get_secure_message()

        secured_items = self.secured_items
        unsecured_items = self.unsecured_items

        # Lets work out what to say
        secured_items_list = ""
        for item in secured_items:
            if item not in self.attempted_items:
                entity = self.find_entity(item)
                if "state_map" in entity:
                    state = entity["state_map"][self.get_state(item)]
                else:
                    state = self.get_state(item)
                name = self.friendly_name(item)
                secured_items_list += " {} is {}, ".format(name, state)

        unsecured_items_list = ""
        for item in unsecured_items:
            entity = self.find_entity(item)
            if "state_map" in entity:
                state = entity["state_map"][self.get_state(item)]
            else:
                state = self.get_state(item)
            name = self.friendly_name(item)
            unsecured_items_list += " {} is {}, ".format(name, state)

        failed_items_list = ""
        for item in self.attempted_items:
            entity = self.find_entity(item)
            if "state_map" in entity:
                state = entity["state_map"][self.get_state(item)]
            else:
                state = self.get_state(item)
            name = self.friendly_name(item)
            failed_items_list += " {} is {}, ".format(name, state)

        message = ""
        if unsecured_items_list != "":
            message += self.get_message("insecure_message")
            message += unsecured_items_list

        if secured_items_list != "":
            message += self.get_message("securing_message")
            message += " " + secured_items_list

        if failed_items_list != "":
            message += self.get_message("failed_message")
            message += " " + failed_items_list

        if unsecured_items_list == "" and failed_items_list == "":
            message += self.get_message("secure_message")
            if self.data["type"] in ["alarm_arm_home", "alarm_arm_away"]:
                message += ". " + self.get_message("alarm_arm_message")
        else:
            message += self.get_message("not_secure_message")
            if self.data["type"] in ["alarm_arm_home", "alarm_arm_away"]:
                message += ". " + self.get_message("alarm_cancel_message")

        # Clean up the message
        message = re.sub(r"^\s+", "", message)
        message = re.sub(r"\s+$", "", message)
        message = re.sub(r"\s+", " ", message)

        return message

    def tts_log(self, message, volume, duration):
        self.log(message)
        sound = self.get_app("Sound")
        sound.tts(message, volume, duration)

    def alarm_alert(self):
        self.log("Alarm going off")

    def arming_alert(self):
        self.log("System is arming")

    def armed_alert(self):
        self.log("System is armed")

    def disarmed_alert(self):
        self.log("System is disarmed")

    def triggered_alert(self):
        self.log("Alarm is about to go off")

    # def notify_alarm(self, entity, old, new):
    #    if "alarm_notify" in self.args:
    #        notifications = self.args["alarm_notify"]
    #        if "tts" in notifications:
    #            self.tts_log(notifications["tts"]["message"], 0.5, 10)
