import appapi

class Log(appapi.APPDaemon):

  def initialize(self):
    return
    self.log("Log Test: Parameter is {}".format(self.args["param1"]))
    self.error("Error Test")

