from appdaemon.adapi import ADAPI

#
# Hello World App
#
# Args:
#


class HelloWorld(ADAPI):
    def initialize(self):
        self.log("Hello from AppDaemon")
        self.log("You are now ready to run Apps!")
