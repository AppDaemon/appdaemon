from enum import Enum

from appdaemon.adapi import ADAPI


class SchedulerTestAppMode(str, Enum):
    """Enum for different modes of the SchedulerTestApp."""

    RUN_EVERY = "run_every"
    RUN_IN = "run_in"


class SchedulerTestApp(ADAPI):
    """
    A test app to verify scheduler functionality.

    Configuration Args:
        mode (str, optional): The mode of operation. Defaults to 'run_every'.
        register_delay (float, optional): Delay before setup in seconds. Defaults to 0.5.

    RUN_EVERY:
        interval (int): Interval in seconds for run_every. Required.
        msg (str): Message to pass to callback. Required.
        start (str, optional): Start time description. Defaults to "now".
    """
    def initialize(self):
        self.set_log_level("DEBUG")
        self.log("SchedulerTestApp initialized")
        self.set_namespace("test")
        self.run_in(self.setup_callback, delay=self.register_delay)

    def setup_callback(self, **kwargs) -> None:
        self.log(f"Running in {self.mode} mode")
        match self.mode:
            case SchedulerTestAppMode.RUN_EVERY:
                match self.args:
                    case {"interval": interval, "msg": str(msg)}:
                        start = self.args.get("start", "now")
                        self.run_every(self.run_every_callback, start=start, interval=interval, msg=msg)
                        return
            case SchedulerTestAppMode.RUN_IN:
                pass
        raise ValueError(f"Invalid arguments for {self.mode}")

    @property
    def mode(self) -> SchedulerTestAppMode:
        return SchedulerTestAppMode(self.args.get("mode", SchedulerTestAppMode.RUN_EVERY))

    @property
    def register_delay(self) -> float:
        return self.args.get("register_delay", 0.5)

    def run_every_callback(self, **kwargs) -> None:
        """Callback function for run_every."""
        self.log(f"Run every callback executed with kwargs: {kwargs}")


class TestSchedulerRunIn(ADAPI):
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


class TestSchedulerRunDaily(ADAPI):
    """A test app to verify run_daily functionality."""

    def initialize(self):
        self.set_log_level("DEBUG")
        self.set_namespace("test")
        self.run_daily(self.scheduled_callback, self.timing)
        self.logger.info(f"{self.__class__.__name__} initialized")

    @property
    def timing(self) -> str:
        """Time string for scheduling."""
        return self.args.get("time", "00:00:05")

    def scheduled_callback(self, **kwargs) -> None:
        """Callback function for run_daily."""
        self.logger.info("Run daily callback executed with kwargs: %s", kwargs)
