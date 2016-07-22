import appapi
import datetime

class Sun(appapi.APPDaemon):

  def initialize(self):
    #return
    self.get_sun_info()
    # Test convert_utc()
    sunset = self.get_state("sun.sun", "next_setting")
    sunset_datetime = self.convert_utc(sunset)
    self.log("Next sunset: {}, {}".format(sunset, sunset_datetime))
    
    # Test
    
    # self.run_in(self.name, self.sun, 5, "Sunrise Test")
    
    # Run at Sunrise
    
    # Example using timedelta
    self.run_at_sunrise(self.sun, datetime.timedelta(minutes = 45).total_seconds(), "Sunrise +45 mins")
    # or you can just do the math yourself
    self.run_at_sunrise(self.sun, 30 * 60, "Sunrise +30 mins")
        
    self.run_at_sunrise(self.sun, -1, "Sunrise -1 sec")
    self.run_at_sunrise( self.sun, 0, "Sunrise")
    self.run_at_sunrise(self.sun, 1, "Sunrise +1 sec")
    
    # Run at Sunset
    
    self.run_at_sunset(self.sun, -1, "Sunset -1 sec")
    self.run_at_sunset(self.sun, 0, "Sunset")
    self.run_at_sunset(self.sun, 1, "Sunset +1 sec")

  def get_sun_info(self):
    self.log("Current sun state: Up = {}, Down = {}".format(self.sun_up(), self.sun_down()))
    self.log("Next sunrise: {}".format(self.sunrise()))
    self.log("Next sunset: {}".format(self.sunset()))
    
  def sun(self, args, kwargs):
    now = datetime.datetime.now()
    self.log("{} {}".format(args[0], now))
    self.get_sun_info()
