import json
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz
from appdaemon.adapi import ADAPI
from appdaemon.utils.functools import clean_http_params_for_urlencode, convert_json, remove_literals

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
]


BASE = {
    "a": 1,
    "b": 2.0,
    "c": "three",
    "d": True,
    "e": False,
    "f": datetime(2025, 9, 22, 12, 0, 0, tzinfo=pytz.utc),
    "g": None
}


def test_clean_http_params_for_urlencode():
    cleaned = clean_http_params_for_urlencode(BASE)
    assert cleaned["a"] == 1
    assert cleaned["b"] == 2.0
    assert cleaned["c"] == "three"
    assert cleaned["d"] == "true"
    assert "e" not in cleaned
    assert isinstance(cleaned["f"], str)
    assert "g" not in cleaned


def test_clean_http_params_for_urlencode_preserves_zero():
    """0 and 0.0 must survive clean_http_params_for_urlencode (0 == False but 0 is not False)."""
    data = {"offset": 0, "price": 0.0, "flag": False, "name": "test"}
    cleaned = clean_http_params_for_urlencode(data)
    assert cleaned["offset"] == 0
    assert cleaned["price"] == 0.0
    assert "flag" not in cleaned
    assert cleaned["name"] == "test"


def test_clean_http_params_for_urlencode_nested():
    """Nested dicts and datetimes are cleaned recursively."""
    data = {
        "outer": {
            "inner": {
                "dt": datetime(2025, 9, 22, 12, 0, 0, tzinfo=pytz.utc),
                "gone": None,
            }
        }
    }
    cleaned = clean_http_params_for_urlencode(data)
    assert cleaned["outer"]["inner"]["dt"] == "2025-09-22T12:00:00+00:00"
    assert "gone" not in cleaned["outer"]["inner"]


SERVICE_CALL = {
    'type': 'call_service',
    'domain': 'notify',
    'service': 'mobile_app_pixel_9a',
    'service_data': {
        'message': 'Phobos Initialized',
        'data': {
            'push': {'sound': {'name': 'Alert_Health_Haptic.caf', 'volume': 0.6, 'critical': 1}},
            'tag': 'phobos-alert',
            'actions': [
                {'action': 'stop_alarms', 'title': 'Stop alarms'},
                {'action': 'silence', 'title': 'Silence'},
            ]
        },
    }
}


def test_clean_http_params_for_urlencode_complex_nested():
    """Complex nested structure (like a service call) is cleaned correctly."""
    cleaned = clean_http_params_for_urlencode(SERVICE_CALL)
    match cleaned:
        case {
            "service_data":
                {"data":
                    {"actions": list(actions),
                        "push": {"sound": {"volume": float(vol)}},
                    },
                },
            }:
            assert vol == 0.6
            for action in actions:
                match action:
                    case {"action": str(), "title": str()}:
                        pass
                    case _:
                        assert False, "Action format incorrect"
        case _:
            assert False, "Structure format incorrect"


def test_remove_literals_strips_none_from_service_call():
    pruned = remove_literals(SERVICE_CALL, (None,))
    assert "timeout" not in pruned["service_data"]


def test_remove_literals_preserves_zero():
    """remove_literals must use identity (is), not equality (==), to avoid 0 == False."""
    data = {"a": 0, "b": 0.0, "c": False, "d": None, "e": "hello"}
    pruned = remove_literals(data, (None, False))
    assert pruned["a"] == 0
    assert pruned["b"] == 0.0
    assert "c" not in pruned
    assert "d" not in pruned
    assert pruned["e"] == "hello"


class TestConvertJson:
    """convert_json is the JSON serializer used by the aiohttp session and websocket."""

    def test_datetime_uses_isoformat(self):
        dt = datetime(2025, 6, 15, 10, 0, 0, tzinfo=pytz.utc)
        result = convert_json({"timestamp": dt})
        parsed = json.loads(result)
        assert parsed["timestamp"] == "2025-06-15T10:00:00+00:00"

    def test_booleans_are_json_booleans(self):
        result = convert_json({"flag": True, "other": False})
        parsed = json.loads(result)
        assert parsed["flag"] is True
        assert parsed["other"] is False

    def test_none_becomes_null(self):
        result = convert_json({"value": None})
        parsed = json.loads(result)
        assert parsed["value"] is None

    def test_zero_preserved(self):
        result = convert_json({"rate": 0, "price": 0.0})
        parsed = json.loads(result)
        assert parsed["rate"] == 0
        assert parsed["price"] == 0.0

    def test_unknown_type_falls_back_to_str(self):
        class Custom:
            def __str__(self):
                return "custom_value"

        result = convert_json({"obj": Custom()})
        parsed = json.loads(result)
        assert parsed["obj"] == "custom_value"


@pytest.mark.asyncio
async def test_call_service_does_not_forward_none_timeout():
    captured: dict[str, object] = {}

    class DummyServices:
        async def call_service(self, namespace, domain, service, data):
            captured["namespace"] = namespace
            captured["domain"] = domain
            captured["service"] = service
            captured["data"] = data
            return {"ok": True}

    class DummyLogger:
        def debug(self, *args, **kwargs):
            pass

    dummy = SimpleNamespace(
        namespace="default",
        name="dummy",
        logger=DummyLogger(),
        AD=SimpleNamespace(services=DummyServices()),
    )
    dummy._check_service = lambda _service: None
    dummy._check_entity = lambda _namespace, _entity_id: None

    result = await ADAPI.call_service.__wrapped__(
        dummy,
        "climate/set_temperature",
        timeout=None,
        entity_id="climate.test",
        temperature=72,
    )

    assert result == {"ok": True}
    assert captured["domain"] == "climate"
    assert captured["service"] == "set_temperature"
    assert captured["data"]["entity_id"] == "climate.test"
    assert captured["data"]["temperature"] == 72
    assert "timeout" not in captured["data"]


class TestSetStateRegression:
    """Regression tests for set_state scenarios from issues #2531, #2464, #2492.

    These simulate what happens when set_state kwargs pass through
    session.post(json=kwargs) with convert_json as the serializer
    (the transparent POST path).
    """

    def test_issue_2531_false_and_zero_attributes(self):
        """Reproduces the exact scenario from issue #2531."""
        kwargs = {
            "state": 1,
            "attributes": {
                "rate": 0,
                "friendly_name": "Test Entity",
                "unit_of_measurement": "GBP/kWh",
                "plunge": False,
                "plunge_start": False,
            },
        }
        result = json.loads(convert_json(kwargs))
        assert result["state"] == 1
        assert result["attributes"]["rate"] == 0
        assert result["attributes"]["plunge"] is False
        assert result["attributes"]["plunge_start"] is False
        assert result["attributes"]["friendly_name"] == "Test Entity"

    def test_issue_2492_zero_float_in_nested_dict(self):
        """Reproduces the scenario from issue #2492 where 0.0 prices vanished."""
        kwargs = {
            "state": "0.08",
            "attributes": {
                "prices": {
                    "2025-11-29T00:00:00+02:00": {"price": 0.0, "intervals": 4},
                    "2025-11-29T11:00:00+02:00": {"price": 0.08, "intervals": 4},
                }
            },
        }
        result = json.loads(convert_json(kwargs))
        prices = result["attributes"]["prices"]
        assert prices["2025-11-29T00:00:00+02:00"]["price"] == 0.0
        assert prices["2025-11-29T11:00:00+02:00"]["price"] == 0.08

    def test_none_attribute_preserved_as_null(self):
        """None values in attributes should become JSON null, not be dropped."""
        kwargs = {
            "state": "on",
            "attributes": {
                "optional_field": None,
                "name": "test",
            },
        }
        result = json.loads(convert_json(kwargs))
        assert "optional_field" in result["attributes"]
        assert result["attributes"]["optional_field"] is None

    def test_state_zero_preserved(self):
        """state=0 must not be dropped."""
        kwargs = {"state": 0, "attributes": {"icon": "mdi:radiator"}}
        result = json.loads(convert_json(kwargs))
        assert result["state"] == 0
