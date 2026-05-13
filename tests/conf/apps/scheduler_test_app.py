from appdaemon.adapi import ADAPI
from appdaemon.utils.str import format_timedelta


class RunInTestApp(ADAPI):
    """A test app to verify run_in functionality."""

    def initialize(self):
        self.set_log_level("DEBUG")
        self.set_namespace("test")
        self.run_in(self.setup_callback, delay=self.register_delay)
        self.logger.info(f"{self.__class__.__name__} initialized")

    @property
    def test_id(self) -> str:
        """Unique identifier for the test run."""
        return self.args.get("test_id", "default_test_id")

    @property
    def register_delay(self) -> float:
        return self.args.get("register_delay", 0.5)

    def setup_callback(self, **kwargs) -> None:
        assert "delay" in self.args, "Delay argument is required"
        delay = self.args["delay"]
        self.logger.info(f"Running with a delay of {delay} seconds")

        self.run_in(self.run_in_callback, delay=delay, test_id=self.test_id)
        # self.log(json.dumps(self.get_scheduler_entries(), default=str, indent=2))

    def run_in_callback(self, **kwargs) -> None:
        """Callback function for run_in."""
        self.logger.info("Run in callback executed with kwargs: %s", kwargs)


class RunEveryTestApp(ADAPI):
    """
    A test app to verify scheduler functionality.

    Configuration Args:
        start (str, optional): Start time description. Defaults to "now".
        interval (int): Interval in seconds for run_every. Required.
        msg (str): Message to pass to callback. Required.
    """
    def initialize(self):
        self.set_log_level("DEBUG")
        self.logger.info("%s initialized",self.__class__.__name__)
        self.set_namespace("test")

        match self.args:
            case {"interval": interval, "msg": str(msg)}:
                self.logger.info("Registering callbacks every %s", format_timedelta(interval))
                self.run_every(
                    self.run_every_callback,
                    interval=interval,
                    msg=msg,
                    start=self.args.get("start", "now"),
                    pin=self.args.get('cb_pin_app'),
                    pin_thread=self.args.get('cb_pin_thread')
                )
                return
        raise ValueError("Invalid arguments for run_every")

    def run_every_callback(self, **kwargs) -> None:
        """Callback function for run_every."""
        self.logger.info("Run every callback executed with kwargs: %s", kwargs)


class TestSchedulerRunDaily(ADAPI):
    """A test app to verify run_daily functionality."""

    def initialize(self):
        self.set_log_level("DEBUG")
        self.run_daily(self.scheduled_callback, self.timing)
        self.logger.info(f"{self.__class__.__name__} initialized")

    @property
    def timing(self) -> str:
        """Time string for scheduling."""
        return self.args.get("time", "00:00:05")

    def scheduled_callback(self, **kwargs) -> None:
        """Callback function for run_daily."""
        self.logger.info("Executed scheduled callback")
        self.logger.info("Run daily callback executed with kwargs: %s", kwargs)
