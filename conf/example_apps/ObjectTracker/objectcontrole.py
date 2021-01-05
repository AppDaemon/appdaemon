###########################################################################################
#                                                                                         #
#  ObjectTracker 2.0                                                                      #
#                                                                                         #
###########################################################################################
#                                                                                         #
#  with ObjectTracker you can track the last updated time from any object in HA           #
#  options are to give the last time an object was updated or the time that has gone by   #
#  you have to set the following options in the appdaemon.cfg:                            #
#                                                                                         #
#  object_type = the type you like to track (switch, input_boolean, sensor, etc)          #
#  time_gone_by = True or False (false for showing last updated time)                     #
#  dir_name = the name of the directory you want the files with times saved               #
#  time_format = any timeformat you like (python strftime type) without %                 #
#                H:M gives 01:27, Y-m-d H:M:S gives 2016-09-04 01:27:25, etc.             #
#  total_objects = the amount off object you want to track                                #
#  object1 = HA entity_ID without the platform part. (for switch.light1 use light1)       #
#  object2 = ...                                                                          #
#  object3 = until you reached you're total_object amount                                 #
#                                                                                         #
#  note that you need to set a new sections in the cfg for each type of object you like   #
#  to track. if you want to track 1 switch and 1 sensor you need to make to sections.     #
#                                                                                         #
#  ObjectTracker depends on general_app_functions.py set as app and set in the cfg as     #
#  [generalvars]                                                                          #
#                                                                                         #
#  Rene Tode ( hass@reot.org )                                                            #
#  version 2.0                                                                            #
#  2016/09/04 Germany                                                                     #
#                                                                                         #
###########################################################################################

import hassapi as hass
import datetime


class objectcontrole(hass.Hass):
    def initialize(self):
        self.listen_state(self.object_controle, self.args["object_type"])
        if self.args["time_gone_by"] == "true" or self.args["time_gone_by"] == "True":
            time = datetime.time(0, 0, 0)
            self.run_minutely(self.object_controle_minutely, time)

    def object_controle(self, entity, attribute, old, new, kwargs):
        fnc = self.get_app("generalvars")
        device, entity_name = self.split_entity(entity)
        for counter in range(1, int(self.args["total_objects"]) + 1):
            device, entity_name = self.split_entity(entity)
            object_name = self.args["object" + str(counter)]
            if entity_name == object_name:
                fnc.update_object_time(
                    object_name,
                    self.friendly_name(entity),
                    self.args["dir_name"],
                    self.args["time_gone_by"],
                    self.args["time_format"],
                    self.args["object_type"],
                )
                fnc.save_last_update_time(self.args["dir_name"], object_name)

    def object_controle_minutely(self, kwargs):
        fnc = self.get_app("generalvars")
        for counter in range(1, int(self.args["total_objects"]) + 1):
            object_name = self.args["object" + str(counter)]
            fnc.update_object_time(
                object_name,
                self.friendly_name(self.args["object_type"] + "." + object_name),
                self.args["dir_name"],
                self.args["time_gone_by"],
                self.args["time_format"],
                self.args["object_type"],
            )
