from appdaemon.adapi import ADAPI
from appdaemon.models.config import AppConfig


class TypedAppConfig(AppConfig, extra="forbid"):
    required_int: int
    optional_str: str = "Hello"


class TypedHelloWorld(ADAPI[TypedAppConfig]):
    def initialize(self):
        self.log("Hello from TypedHelloWorld")
        self.log(f"Config type: {type(self.config_model)}")
        self.log("Config values are accessible in both way:")
        self.log(f" - Legacy: {self.args['required_int']=}")
        self.log(f" -  Typed: {self.config_model.required_int=}")


class HelloWorld(ADAPI):
    def initialize(self):
        self.log("Hello from AppDaemon")
        self.log("You are now ready to run Apps!")
        self.log(f"My kwarg: {self.args.get('my_kwarg', 'not set')}")
