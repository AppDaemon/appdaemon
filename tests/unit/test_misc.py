import pytest
from appdaemon.utils.misc import deep_compare

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


def test_deep_compare_missing_nested_key_returns_false() -> None:
    check = {"guest": {"sleepguest": True}}
    data = {"guest": {}}

    assert deep_compare(check, data) is False


def test_deep_compare_equal_nested_dict_returns_true() -> None:
    check = {"guest": {"sleepguest": True}}
    data = {"guest": {"sleepguest": True, "other": "value"}}

    assert deep_compare(check, data) is True


def test_deep_compare_missing_top_level_key_returns_false() -> None:
    check = {"sleepguest": True}
    data = {}

    assert deep_compare(check, data) is False
