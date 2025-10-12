from copy import deepcopy
from datetime import datetime

import pytest
import pytz
from appdaemon.utils import clean_http_kwargs, clean_kwargs, remove_literals

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


def test_clean_kwargs():
    cleaned = clean_kwargs(BASE)
    pruned = remove_literals(BASE, (None,))
    assert isinstance(cleaned["f"], str)

    assert cleaned["a"] == 1
    assert cleaned["b"] == 2.0
    assert cleaned["c"] == "three"
    assert cleaned["d"] is True
    assert cleaned["e"] is False
    assert "g" not in pruned

    kwargs = deepcopy(BASE)

    kwargs["nested"] = deepcopy(BASE)
    kwargs["nested"]["extra"] = deepcopy(BASE)
    cleaned = clean_kwargs(kwargs)
    assert isinstance(cleaned["nested"]["extra"]["f"], str)


def test_clean_http_kwargs():
    cleaned = clean_http_kwargs(BASE)
    assert isinstance(cleaned["f"], str)
    assert cleaned["d"] == "true"
    assert "e" not in cleaned
    assert "g" not in cleaned


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


def test_websocket_service_call_kwargs():
    cleaned = clean_kwargs(SERVICE_CALL)
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
            assert False, "Action format incorrect"

    pruned = remove_literals(SERVICE_CALL, (None,))
    assert "timeout" not in pruned["service_data"]
