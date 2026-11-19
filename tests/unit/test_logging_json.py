import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from appdaemon.logging import JSONFormatter, Logging, LogSubscriptionHandler
from appdaemon.models.config.log import AppDaemonLogConfig
from pydantic import ValidationError

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]

MakeLogging = Callable[[dict], Logging]


def json_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


JSON_MAIN_LOG = {"main_log": {"filename": "STDOUT", "output_format": "json"}}


def test_each_record_is_one_json_object_per_line(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    logger = json_log.get_logger()
    logger.info("hello %s", "world")
    logger.warning("second")

    records = json_lines(capsys.readouterr().out)

    assert [(r["level"], r["message"]) for r in records] == [("INFO", "hello world"), ("WARNING", "second")]
    assert records[0]["logger"] == logger.name
    assert records[0]["app"] == logger.name
    assert set(records[0]) == {"timestamp", "level", "app", "logger", "message"}


def test_app_field_matches_appname(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    json_log.get_logger().getChild("my_app").info("from an app")
    json_log.get_logger().getChild("_scheduler").info("from a module")

    app_record, module_record = json_lines(capsys.readouterr().out)

    assert app_record["app"] == "my_app"
    assert module_record["app"] == "AppDaemon"


def test_exception_is_kept_on_one_line(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    try:
        1 / 0
    except ZeroDivisionError:
        json_log.get_logger().error("failed", exc_info=True)

    out = capsys.readouterr().out
    (record,) = json_lines(out)

    assert out.count("\n") == 1
    assert record["message"] == "failed"
    assert record["exception"].startswith("Traceback")
    assert "ZeroDivisionError" in record["exception"]


def test_stack_info_is_included(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    json_log.get_logger().info("where", stack_info=True)

    (record,) = json_lines(capsys.readouterr().out)

    assert record["stack_info"].startswith("Stack (most recent call last)")


def test_non_ascii_round_trips(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    json_log.get_logger().info("caf\u00e9 \u2603 %s", "\u65e5\u672c")

    (record,) = json_lines(capsys.readouterr().out)

    assert record["message"] == "caf\u00e9 \u2603 \u65e5\u672c"


def test_timestamp_follows_appdaemon_clock_and_time_zone(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    tz = ZoneInfo("America/New_York")
    warped = datetime(2025, 6, 20, 12, 30, 15, 123456, tzinfo=ZoneInfo("UTC"))
    json_log.set_tz(tz)
    json_log.AD = SimpleNamespace(sched=SimpleNamespace(is_realtime=lambda: False, get_now_sync=lambda: warped))

    json_log.get_logger().info("time travel")

    (record,) = json_lines(capsys.readouterr().out)
    assert record["timestamp"] == "2025-06-20T08:30:15.123456-04:00"


def test_timestamp_has_an_offset_without_a_time_zone(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    json_log = make_logging(JSON_MAIN_LOG)
    json_log.get_logger().info("local time")

    (record,) = json_lines(capsys.readouterr().out)
    assert datetime.fromisoformat(record["timestamp"]).utcoffset() is not None


def test_every_log_type_can_use_json(make_logging: MakeLogging) -> None:
    logs = make_logging(
        {
            "main_log": {"output_format": "json"},
            "error_log": {"output_format": "json"},
            "diag_log": {"output_format": "json"},
            "user_log": {"output_format": "json"},
        }
    )

    for log in ("main_log", "error_log", "diag_log", "user_log", "access_log"):
        assert isinstance(logs.config[log]["formatter"], JSONFormatter), log


def test_default_output_is_unchanged_text(make_logging: MakeLogging, capsys: pytest.CaptureFixture[str]) -> None:
    logs = make_logging({"main_log": {}})
    logger = logs.get_logger()

    logger.info("hello %s", "world")

    out = capsys.readouterr().out
    assert re.fullmatch(rf"\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{{6}} INFO {logger.name}: hello world\n", out)


def test_log_subscription_receives_json_line() -> None:
    ad = MagicMock()
    handler = LogSubscriptionHandler(ad, "main_log")
    handler.setFormatter(JSONFormatter(now=datetime.now))
    record = logging.LogRecord("AppDaemon.my_app", logging.INFO, __file__, 1, "hello %s", ("world",), None)

    handler.emit(record)

    data = ad.thread_async.call_async_no_wait.call_args.args[2]["data"]
    assert data["app_name"] == "my_app"
    assert data["message"] == "hello world"
    assert data["asctime"]
    assert json.loads(data["formatted_message"])["message"] == "hello world"


def test_unknown_output_format_is_rejected(make_logging: MakeLogging) -> None:
    with pytest.raises(ValueError, match="output_format"):
        make_logging({"main_log": {"output_format": "xml"}})


def test_config_model_rejects_unknown_output_format() -> None:
    assert AppDaemonLogConfig.model_validate({"output_format": "json"}).output_format == "json"
    with pytest.raises(ValidationError):
        AppDaemonLogConfig.model_validate({"output_format": "xml"})
