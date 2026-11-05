from appdaemon.adapi import ADAPI


class PinThreadTester(ADAPI):
    def initialize(self):
        self.set_log_level("DEBUG")
        self.set_namespace("test")
        self.run_in(
            self.example_callback,
            delay=self.args.get("register_delay", 0.2),
            pin=self.args.get("cb_pin_app"),
            pin_thread=self.args.get("cb_pin_thread")
        )
        self.logger.info("%s initialized", __class__.__name__)

    def example_callback(self, **kwargs):
        self.logger.info('Example callback: %s', kwargs)
