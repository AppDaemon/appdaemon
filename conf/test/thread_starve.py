import appapi
import datetime
import time

class ThreadStarve(appapi.APPDaemon):

  def initialize(self):
    return
    time = datetime.datetime.now() + datetime.timedelta(seconds=5)
    self.run_every(self.run_every_c, time, 1)

  def run_every_c(self, args, kwargs):
    self.log("ThreadStarve: Running once")
    time.sleep(15)
    