import appapi
import datetime

class Schedule(appapi.APPDaemon):

  def initialize(self):
    return
    # Run a few timers and pass parameters
    
    self.run_in(self.run_in_c, 5, 5, 10, title = "run_in5", test = "Another Param")
    self.run_in(self.run_in_c, 10, 10, 15, title = "run_in10", test = "Another Param")
    self.run_in(self.run_in_c, 15, 15, 20, title = "run_in15", test = "Another Param")
    self.run_in(self.run_in_c, 20, 20, 25, title = "run_in20", test = "Another Param")

    # run_in with no params
    
    self.run_in(self.run_innoargs_c, 5)

    # Create a timer and then cancel it
    
    handle = self.run_in(self.run_in_c, 15)
    self.cancel_timer(handle)
    
    # Run at a specific time
    
    #runtime = datetime.time(11, 14, 0)
    runtime = (datetime.datetime.now() + datetime.timedelta(seconds=20)).time()
    handle = self.run_once(self.run_once_c, runtime)
    
    # Run every day at a specific time
    
    # e.g.time = datetime.time(12, 49, 0)
    runtime = (datetime.datetime.now() + datetime.timedelta(seconds=25)).time()
    self.run_daily(self.run_daily_c, runtime)
    
    # Run Hourly starting 1 hour from now
    
    self.run_hourly(self.run_hourly_c, None)
    
    # Run Hourly on the hour
    
    time = datetime.time(0, 0, 0)
    self.run_hourly(self.run_hourly_c, time)
    
    # Run Every Minute starting in 1 minute
    
    self.run_minutely(self.run_minutely_c, None)
    
    # Run Every Minute on the minute
    
    time = datetime.time(0, 0, 0)
    self.run_minutely(self.run_minutely_c, time)

    # Run every 13 seconds starting in 10 seconds time
    
    time = datetime.datetime.now() + datetime.timedelta(seconds=10)
    self.run_every(self.run_every_c, time, 13)
    
    # Attempt some scheduler abuse ...
    
    #for x in range(1, 10000):
    #  handle = self.run_in(self.run_innoargs, 5)

   
  def run_daily_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("Running daily at {}".format(now))
    
  def run_once_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("Running once at {}".format(now))
    
  def run_every_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("Running once at {}".format(now))
    
  def run_in_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("run in {}, extra positional {}, title {}, test {}, at {}".format(args[0], args[1], kwargs["title"], kwargs["test"], now))

  def run_innoargs_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("run_innoargs at {}".format(now))
    
  def run_hourly_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("run hourly at {}".format(now))

  def run_minutely_c(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("run every minute at {}".format(now))
    
