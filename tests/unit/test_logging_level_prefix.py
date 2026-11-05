import logging
import re
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from appdaemon.logging import Logging, LogSubscriptionHandler, SyslogLevelPrefixFormatter
from appdaemon.models.config.log import AppDaemonLogConfig
from pydantic import ValidationError

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]

MakeLogging = Callable[[dict], Logging]

TEXT_LINE = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{6} [A-Z]+ \S+: "


@pytest.mark.parametrize(
    ("levelno", "priority"),
    [
        (logging.CRITICAL + 10, 2),
        (logging.CRITICAL, 2),
        (logging.ERROR + 5, 3),
        (logging.ERROR, 3),
        (logging.WARNING, 4),
        (logging.INFO + 5, 6),
        (logging.INFO, 6),
        (logging.DEBUG + 5, 7),
        (logging.DEBUG, 7),
        (logging.NOTSET, 7),
    ],
)
def test_priority_mapping(levelno: int, priority: int) -> None:
    assert SyslogLevelPrefixFormatter.priority(levelno) == priority


@pytest.mark.parametrize("filename", ["STDOUT", "STDERR"])
def test_stream_lines_carry_their_priority(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str], filename: str) -> None:
    logs = make_logging({"prefixed_log": {"filename": filename, "level_prefix": "syslog", "level": "DEBUG"}})
    logger = logs.config["prefixed_log"]["logger"]

    logger.debug("debug message")
    logger.info("info %s", "message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")

    captured = capsys.readouterr()
    lines = (captured.out + captured.err).splitlines()
    assert [line[:3] for line in lines] == ["<7>", "<6>", "<4>", "<3>", "<2>"]
    assert re.fullmatch(f"<6>{TEXT_LINE}info message", lines[1])


def test_every_line_of_a_traceback_is_prefixed(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    logs = make_logging({"main_log": {"filename": "STDOUT", "level_prefix": "syslog"}})

    try:
        1 / 0
    except ZeroDivisionError:
        logs.get_logger().error("failed", exc_info=True)

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) > 2
    assert all(line.startswith("<3>") for line in lines)
    assert lines[-1] == "<3>ZeroDivisionError: division by zero"


def test_no_prefix_by_default(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    logs = make_logging({"main_log": {"filename": "STDOUT"}})

    logs.get_logger().info("plain")

    assert re.fullmatch(f"{TEXT_LINE}plain\n", capsys.readouterr().out)


def test_log_subscriptions_are_not_prefixed(make_logging: MakeLogging) -> None:
    logs = make_logging({"main_log": {"filename": "STDOUT", "level_prefix": "syslog"}})
    ad = MagicMock()
    handler = LogSubscriptionHandler(ad, "main_log")
    handler.setFormatter(logs.config["main_log"]["formatter"])

    handler.emit(logging.LogRecord("AppDaemon", logging.INFO, __file__, 1, "hello", None, None))

    data = ad.thread_async.call_async_no_wait.call_args.args[2]["data"]
    assert re.fullmatch(f"{TEXT_LINE}hello", data["formatted_message"])


def test_file_logs_are_refused(make_logging: MakeLogging, tmp_path: Path) -> None:
    path = tmp_path / "prefixed.log"

    with pytest.raises(ValueError, match="STDOUT or STDERR"):
        make_logging({"file_log": {"filename": str(path), "level_prefix": "syslog"}})

    assert not path.exists()


def test_unknown_level_prefix_is_rejected(make_logging: MakeLogging) -> None:
    with pytest.raises(ValueError, match="level_prefix"):
        make_logging({"main_log": {"level_prefix": "rfc5424"}})


def test_config_model_validates_level_prefix() -> None:
    assert AppDaemonLogConfig.model_validate({"level_prefix": "syslog"}).level_prefix == "syslog"
    assert AppDaemonLogConfig.model_validate({}).level_prefix is None
    with pytest.raises(ValidationError):
        AppDaemonLogConfig.model_validate({"level_prefix": "rfc5424"})
