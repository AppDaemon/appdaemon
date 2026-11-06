from collections.abc import Callable

import pytest
from appdaemon.logging import Logging

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


def test_stream_filenames_write_to_matching_stream(make_logging: Callable[[dict], Logging], capsys: pytest.CaptureFixture[str]) -> None:
    logs = make_logging(
        {
            "out_log": {"filename": "STDOUT"},
            "err_log": {"filename": "STDERR"},
        }
    )

    logs.config["out_log"]["logger"].info("to stdout")
    logs.config["err_log"]["logger"].info("to stderr")

    captured = capsys.readouterr()
    assert "to stdout" in captured.out
    assert "to stdout" not in captured.err
    assert "to stderr" in captured.err
    assert "to stderr" not in captured.out
