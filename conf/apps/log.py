import homeassistant as ha
import appapi

class Log(appapi.APPDaemon):

  def initialize(self):
    return
    self.logger.info("Log Test: Parameter is {}".format(self.args["param1"]))
