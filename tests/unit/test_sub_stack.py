import pytest
from appdaemon.adapi import ADAPI

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


def _log(msg):
    """Stand-in for ADAPI.log/error/etc.

    ``_sub_stack`` reads ``stack[2]`` — two frames above itself — because it is
    designed to be called from inside a logging wrapper. Tests therefore need
    an intermediate frame so the resolved caller is deterministic.
    """
    return ADAPI._sub_stack(msg)


def test_non_string_returned_unchanged():
    payload = {"key": "value"}
    assert ADAPI._sub_stack(payload) is payload
    assert ADAPI._sub_stack(123) == 123
    assert ADAPI._sub_stack(None) is None


def test_plain_string_returned_unchanged():
    msg = "nothing special here"
    assert _log(msg) == msg


def test_module_placeholder_substituted():
    result = _log("called from __module__")
    assert "__module__" not in result
    assert result.startswith("called from ")


def test_line_placeholder_substituted():
    result = _log("line=__line__")
    assert "__line__" not in result
    assert result.startswith("line=")
    assert result[len("line=") :].isdigit()


def test_function_placeholder_substituted():
    def outer_caller():
        return _log("in __function__")

    assert outer_caller() == "in outer_caller"


def test_multiple_placeholders_in_same_message():
    def outer_caller():
        return _log("__function__ at __line__")

    result = outer_caller()
    assert "__function__" not in result
    assert "__line__" not in result
    assert result.startswith("outer_caller at ")
