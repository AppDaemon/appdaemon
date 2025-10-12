from appdaemon.adapi import ADAPI


class HelloWorld(ADAPI):
    def initialize(self):
        self.log("Hello from AppDaemon")
        self.log("You are now ready to run Apps!")
        self.log(f"My kwarg: {self.args.get('my_kwarg', 'not set')}")
