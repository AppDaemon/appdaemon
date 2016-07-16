import homeassistant as ha
import appapi
import datetime

class Schedule(appapi.APPDaemon):

  def initialize(self):
    return
    # Run a few timers and pass parameters
    
    #ha.run_in(self.name, self.run_in, 5, 5, 10, title = "run_in5", test = "Another Param")
    #ha.run_in(self.name, self.run_in, 10, 10, 15, title = "run_in10", test = "Another Param")
    #ha.run_in(self.name, self.run_in, 15, 15, 20, title = "run_in15", test = "Another Param")
    #ha.run_in(self.name, self.run_in, 20, 20, 25, title = "run_in20", test = "Another Param")

    # run_in with no params
    
    #ha.run_in(self.name, self.run_innoargs, 5)

    # Create a timer and then cancel it
    
    #handle = ha.run_in(self.name, self.run_in, 15)
    #ha.cancel_timer(self.name, handle)
    
    # Run at a specific time
    
    #runtime = datetime.time(11, 14, 0)
    #runtime = (datetime.datetime.now() + datetime.timedelta(seconds=20)).time()
    #handle = ha.run_once(self.name, self.run_once, runtime)
    
    # Run every day at a specific time
    
    # e.g.time = datetime.time(12, 49, 0)
    #runtime = (datetime.datetime.now() + datetime.timedelta(seconds=25)).time()
    #ha.run_daily(self.name, self.run_daily, runtime)
    
    # Run Hourly starting 1 hour from now
    
    #ha.run_hourly(self.name, self.run_everyhour, None)
    
    # Run Hourly on the hour
    
    #time = datetime.time(0, 0, 0)
    #ha.run_hourly(self.name, self.run_everyhour, time)
    
    # Run Every Minute starting in 1 minute
    
    #ha.run_minutely(self.name, self.run_minutely, None)
    
    # Run Every Minute on the minute
    
    #time = datetime.time(0, 0, 0)
    #ha.run_minutely(self.name, self.run_minutely, time)

    # Run every 13 seconds starting in 10 seconds time
    
    # time = datetime.datetime.now() + datetime.timedelta(seconds=10)
    # ha.run_every(self.name, self.run_every, time, 10)
    
    # Attempt some scheduler abuse ...
    
    #for x in range(1, 10000):
    #  handle = ha.run_in(self.name, self.run_innoargs, 5)

   
  def run_daily(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("Running daily at {}".format(now))
    
  def run_once(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("Running once at {}".format(now))
    
  def run_every(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("Running once at {}".format(now))
    
  def run_in(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("run in {}, extra positional {}, title {}, test {}, at {}".format(args[0], args[1], kwargs["title"], kwargs["test"], now))
    self.error.info("Error Test")

  def run_innoargs(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("run_innoargs at {}".format(now))
    
  def run_everyhour(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("run hourly at {}".format(now))

  def run_minutely(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("run every minute at {}".format(now))
    
