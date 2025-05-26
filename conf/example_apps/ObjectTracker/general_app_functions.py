###########################################################################################
#                                                                                         #
#  some general function which can be called from other Apps                              #
#  update_object_time: sets the state from objects in HA. object will look like:          #
#                      'controle.friendly_name_from_entity'                               #
#                      state can be last time updated or time gone by since last update   #
#  check_last_update_time: checks when the last time was that a sensor was updated        #
#  save_last_update_time: saves the time that an object is updated to a file in a dir     #
#                         you can define. the file will have the name: lut_entity_id.py    #
#  reformat_time: changed a timeformat from H:M:S to %H:%M:%S                             #
#                                                                                         #
#  Rene Tode ( hass@reot.org )                                                            #
#  version 2.0                                                                            #
#  2016/09/04 Germany                                                                     #
#                                                                                         #
###########################################################################################

import datetime as datetime
import platform

import hassapi as hass


class general_fnc(hass.Hass):
    def initialize(self):
        return

    def update_object_time(
        self,
        object_name,
        object_friendly_name,
        dir_name,
        time_gone_by,
        time_format,
        object_type,
    ):
        update_time = datetime.datetime.now()
        new_time_format = self.reformat_time(time_format)

        if time_gone_by == "true" or time_gone_by == "True":
            str_old_time = self.check_last_update_time(dir_name, object_name)
            try:
                old_time = datetime.datetime.strptime(str_old_time, "%Y-%m-%d %H:%M:%S")
            except Exception:
                self.log("strptime gives err on: " + str_old_time, level="INFO")
                return
            gone_by_time = update_time - old_time
            str_update_time = str(gone_by_time)[:-7] + " ago"
        else:
            str_update_time = update_time.strftime(new_time_format)

        new_entity = object_friendly_name.replace(" ", "_")
        new_entity = new_entity.replace(".", "")
        new_entity = new_entity.replace("(", "")
        new_entity = new_entity.replace(")", "")
        self.set_state("controle." + new_entity, state=str_update_time)

    @staticmethod
    def check_last_update_time(objects_dir, object_name):
        if platform.system() == "windows":
            complete_file_name = objects_dir + "\\lut_" + object_name + ".py"
        else:
            complete_file_name = objects_dir + "/lut_" + object_name + ".py"
        try:
            set_object = open(complete_file_name, "r")
            old_time = set_object.readline()
            set_object.close()
            return old_time
        except Exception:
            return "2000-01-01 00:00:00"

    def save_last_update_time(self, objects_dir, object_name):
        if platform.system() == "windows":
            complete_file_name = objects_dir + "\\lut_" + object_name + ".py"
        else:
            complete_file_name = objects_dir + "/lut_" + object_name + ".py"

        str_complete_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            set_object = open(complete_file_name, "w")
            set_object.write(str_complete_time)
            set_object.close()
        except Exception:
            self.log(
                "couldn't save the time from: " + object_name + " in " + complete_file_name,
                level="INFO",
            )

    @staticmethod
    def reformat_time(time_format):
        new_time_format = ""
        for counter in range(0, len(time_format)):
            if time_format[counter] != " " and time_format[counter] != "-" and time_format[counter] != ":" and time_format[counter] != "\\":
                new_time_format = new_time_format + "%" + time_format[counter]
            else:
                new_time_format = new_time_format + time_format[counter]
        return new_time_format
