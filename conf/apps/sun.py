import homeassistant as ha
import appapi
import datetime

class Sun(appapi.APPDaemon):

  def initialize(self):
  
    self.get_sun_info()
    
    # Test
    
    # ha.run_in(self.name, self.sun, 5, "Sunrise Test")
    
    # Run at Sunrise
        
    ha.run_at_sunrise(self.name, self.sun, -1, "Sunrise -1")
    ha.run_at_sunrise(self.name, self.sun, 0, "Sunrise")
    ha.run_at_sunrise(self.name, self.sun, 1, "Sunrise +1")
    
    # Run at Sunset
    
    ha.run_at_sunset(self.name, self.sun, -1, "Sunset -1")
    ha.run_at_sunset(self.name, self.sun, 0, "Sunset")
    ha.run_at_sunset(self.name, self.sun, 1, "Sunset +1")

  def get_sun_info(self):
    self.logger.info("Current sun state: {}".format(ha.sun_state()))
    self.logger.info("Next sunrise: {}".format(ha.sunrise()))
    self.logger.info("Next sunset: {}".format(ha.sunset()))
    
  def sun(self, args, kwargs):
    now = datetime.datetime.now()
    self.logger.info("{} {}".format(args[0], now))
    self.get_sun_info()
