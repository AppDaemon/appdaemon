import appapi

class Class1(appapi.APPDaemon):

  def initialize(self):
    return
    self.log("Class 1: Parameter is {}".format(self.args["param1"]))
    self.run_in(self.run_once_c, 5)

  def run_once_c(self, args, kwargs):
    self.log("{}: Running once".format(self.args["param1"]))
    
class Class2(appapi.APPDaemon):

  def initialize(self):
    return
    self.log("Class 2: Parameter is {}".format(self.args["param1"]))
    self.run_in(self.run_once_c, 5)

  def run_once_c(self, args, kwargs):
    self.log("{}: Running once".format(self.args["param1"]))