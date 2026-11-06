"""Tests for the /livez and /readyz health endpoints and the auth they share with the API."""

import asyncio
import functools
import hmac
import json
from datetime import timedelta
from pathlib import Path
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, create_autospec

import bcrypt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from appdaemon import health, utility_loop
from appdaemon.app_management import INITIALIZING, AppManagement
from appdaemon.http import HTTP, route_secure, secure, securedata
from appdaemon.models.config import MainConfig
from appdaemon.plugin_management import PluginManagement
from appdaemon.plugins.hass.hassplugin import PluginBase
from appdaemon.utility_loop import Utility

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.asyncio,
]

FLOOR = health.MIN_PROGRESS_TIMEOUT
CONTENT_TYPE = "application/health+json"


def _entity(state: str, last_changed: str = "2026-11-06T10:00:00+00:00") -> dict:
    return {"state": state, "last_changed": last_changed}


def _add_plugin(ad: MagicMock, name: str, *, ready: bool = True, active: bool = True) -> None:
    plugin = create_autospec(PluginBase, instance=True)
    plugin.name = name
    plugin.is_ready = ready
    ad.plugins.config[name] = MagicMock(disabled=False)
    ad.plugins.plugin_objs[name.lower()] = {"object": plugin, "active": active, "name": name}


def _make_ad(
    plugins: dict[str, bool] | None = None,
    app_states: dict[str, str] | None = None,
    utility_delay: float = 1,
) -> MagicMock:
    """A mocked AppDaemon around the real components the health checks read."""
    ad = MagicMock()
    ad.stopping = False
    ad.apps_enabled = True
    ad.config_dir = Path("/nonexistent/appdaemon")
    ad.config.utility_delay = timedelta(seconds=utility_delay)
    ad.state.state = {"admin": {f"app.{n}": _entity(s) for n, s in (app_states or {}).items()}}
    ad.utility = Utility(ad)
    ad.utility.last_progress = monotonic()
    ad.utility.startup_complete = True
    ad.utility.loop_task = MagicMock(done=MagicMock(return_value=False))
    ad.app_management = AppManagement(ad)
    ad.plugins = PluginManagement(ad, {})
    for name, ready in {"HASS": True}.items() if plugins is None else plugins.items():
        _add_plugin(ad, name, ready=ready)
    return ad


def _make_http(ad: MagicMock, password: str | None = None) -> HTTP:
    http_cfg = {"url": "http://127.0.0.1:5050"} | ({"password": password} if password else {})
    ad_cfg = {"latitude": 0, "longitude": 0, "elevation": 0, "time_zone": "UTC", "config_dir": ".", "config_file": "appdaemon.yaml"}
    http = HTTP(ad, MainConfig.model_validate({"appdaemon": ad_cfg, "http": http_cfg}))
    http.work_factor = 4  # keeps the test cookies cheap
    ad.http = http
    return http


async def _get(http: HTTP, path: str, **kwargs) -> tuple[int, dict, str]:
    async with TestClient(TestServer(http.app)) as client:
        resp = await client.get(path, **kwargs)
        return resp.status, dict(resp.headers), await resp.text()


async def _health(http: HTTP, path: str, **kwargs) -> tuple[int, dict]:
    status, _, text = await _get(http, path, **kwargs)
    return status, json.loads(text)


def _cookie(password: str, rounds: int = 4) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


class _Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    clock = _Clock()
    monkeypatch.setattr(health, "monotonic", clock)
    monkeypatch.setattr(utility_loop, "monotonic", clock)
    return clock


def _stalled_for(ad: MagicMock, clock: _Clock, seconds: float) -> dict:
    ad.utility.last_progress = clock.now - seconds
    return health.liveness_checks(ad)["utility:lastProgress"][0]


# readyz


async def test_readyz_pass():
    http = _make_http(_make_ad(app_states={"a": "idle"}))
    async with TestClient(TestServer(http.app)) as client:
        resp = await client.get("/readyz")
        body = await resp.json(content_type=None)
    assert resp.status == 200
    assert resp.content_type == CONTENT_TYPE
    assert resp.headers["Cache-Control"] == "no-store"
    assert body["status"] == "pass"
    assert body["checks"]["plugin:HASS"][0]["status"] == "pass"
    assert body["checks"]["apps:failed"][0]["observedValue"] == 0


async def test_readyz_warn_on_failed_apps_but_not_other_states():
    ad = _make_ad(app_states={"good": "idle", "bad": "initialize_error", "worse": "compile_error", "dep": "dependency_error"})
    status, body = await _health(_make_http(ad), "/readyz")
    assert status == 200
    assert body["status"] == "warn"
    check = body["checks"]["apps:failed"][0]
    assert (check["status"], check["observedValue"], check["output"]) == ("warn", 2, "failed: bad, worse")


async def test_readyz_has_no_apps_check_when_apps_are_disabled():
    ad = _make_ad()
    ad.apps_enabled = False
    _, body = await _health(_make_http(ad), "/readyz")
    assert "apps:failed" not in body["checks"]


async def test_readyz_fail_on_disconnected_plugin():
    status, body = await _health(_make_http(_make_ad(plugins={"HASS": False, "MQTT": True})), "/readyz")
    assert status == 503
    assert body["status"] == "fail"
    assert body["checks"]["plugin:HASS"][0]["status"] == "fail"
    assert body["checks"]["plugin:MQTT"][0]["status"] == "pass"


async def test_readyz_follows_plugin_stopped_and_started_even_if_is_ready_stays_set():
    """MQTT never clears ``ready_event``, so only ``notify_plugin_stopped`` marks its outage."""
    ad = _make_ad(plugins={"MQTT": True})
    ad.loop = asyncio.get_running_loop()
    ad.events.process_event = AsyncMock()
    ad.app_management.check_app_updates = AsyncMock()
    http = _make_http(ad)

    assert (await _health(http, "/readyz"))[0] == 200
    await ad.plugins.notify_plugin_stopped("MQTT", "mqtt")
    status, body = await _health(http, "/readyz")
    assert (status, body["checks"]["plugin:MQTT"][0]["observedValue"]) == (503, "disconnected")

    ad.plugins.plugin_objs["mqtt"]["active"] = True  # what notify_plugin_started sets
    assert (await _health(http, "/readyz"))[0] == 200


async def test_readyz_fail_on_plugin_that_never_loaded():
    ad = _make_ad()
    ad.plugins.plugin_objs.clear()
    status, body = await _health(_make_http(ad), "/readyz")
    assert status == 503
    assert body["checks"]["plugin:HASS"][0]["observedValue"] == "not loaded"


async def test_readyz_skips_disabled_plugin():
    ad = _make_ad()
    ad.plugins.config["OFF"] = MagicMock(disabled=True)
    _, body = await _health(_make_http(ad), "/readyz")
    assert "plugin:OFF" not in body["checks"]


async def test_readyz_fail_before_startup_complete():
    ad = _make_ad()
    ad.utility.startup_complete = False
    status, body = await _health(_make_http(ad), "/readyz")
    assert status == 503
    assert body["checks"]["appdaemon:startup"][0]["status"] == "fail"


async def test_readyz_fail_while_stopping():
    ad = _make_ad()
    ad.stopping = True
    assert (await _health(_make_http(ad), "/readyz"))[0] == 503


# livez


async def test_livez_pass():
    http = _make_http(_make_ad())
    status, headers, text = await _get(http, "/livez")
    check = json.loads(text)["checks"]["utility:lastProgress"][0]
    assert (status, headers["Content-Type"].split(";")[0]) == (200, CONTENT_TYPE)
    assert (check["status"], check["observedUnit"]) == ("pass", "s")


async def test_livez_threshold_floor_is_300s(clock):
    ad = _make_ad()
    assert _stalled_for(ad, clock, FLOOR)["status"] == "pass"
    check = _stalled_for(ad, clock, FLOOR + 1)
    assert (check["status"], check["observedValue"], check["observedUnit"]) == ("fail", FLOOR + 1, "s")
    assert FLOOR == 300


async def test_livez_threshold_scales_with_utility_delay(clock):
    ad = _make_ad(utility_delay=60)
    assert _stalled_for(ad, clock, 590)["status"] == "pass"
    assert _stalled_for(ad, clock, 601)["status"] == "fail"


async def test_livez_fail_status_code_on_stale_loop(clock):
    ad = _make_ad()
    ad.utility.last_progress = clock.now - FLOOR - 5
    status, body = await _health(_make_http(ad), "/livez")
    assert (status, body["status"]) == (503, "fail")


async def test_livez_fail_when_loop_task_died_unless_stopping():
    ad = _make_ad()
    ad.utility.loop_task.done.return_value = True
    http = _make_http(ad)
    assert (await _health(http, "/livez"))[0] == 503
    ad.stopping = True
    assert (await _health(http, "/livez"))[0] == 200


async def test_livez_pass_before_first_progress():
    ad = _make_ad()
    ad.utility.last_progress = None
    assert (await _health(_make_http(ad), "/livez"))[0] == 200


async def test_livez_ignores_disconnected_plugin_and_failed_apps():
    ad = _make_ad(plugins={"HASS": False}, app_states={"bad": "initialize_error"})
    status, body = await _health(_make_http(ad), "/livez")
    assert status == 200
    assert set(body["checks"]) == {"utility:lastProgress"}


async def test_livez_stall_without_initializing_app_says_so(clock):
    output = _stalled_for(_make_ad(), clock, FLOOR + 1)["output"]
    assert output == f"utility loop has made no progress in {FLOOR + 1:g}s"


async def test_livez_names_the_longest_initializing_app(clock):
    ad = _make_ad()
    ad.state.state["admin"] |= {
        "app.newer": _entity(INITIALIZING, "2026-11-06T10:05:00+00:00"),
        "app.older": _entity(INITIALIZING, "2026-11-06T10:02:11+00:00"),
        "app.idle": _entity("idle", "2026-11-06T09:00:00+00:00"),
    }
    output = _stalled_for(ad, clock, FLOOR + 12)["output"]
    assert output == f"no progress in {FLOOR + 12:g}s; app 'older' has been initializing since 2026-11-06T10:02:11+00:00"


def _app_management_with_fake_state(utility: Utility, init) -> tuple[AppManagement, dict]:
    ad = MagicMock()
    ad.utility = utility
    entities: dict[str, dict] = {}
    ad.state.state = {"admin": entities}
    am = AppManagement(ad)
    am.objects["app"] = MagicMock(object=MagicMock(initialize=init))
    am.app_module_rel_path = MagicMock()

    async def set_state(name: str, state: str, **kwargs):
        entities[f"app.{name}"] = _entity(state, "2026-11-06T10:02:11+00:00")

    am.set_state = set_state
    return am, entities


async def test_livez_stays_live_through_a_long_reload_of_apps_that_keep_initializing(clock):
    utility = Utility(MagicMock())
    utility.record_progress()

    async def init():
        pass

    am, entities = _app_management_with_fake_state(utility, init)
    ad = _make_ad()
    ad.utility, ad.app_management = utility, am
    for _ in range(3):  # each gap is under the threshold, the total is well over it
        clock.now += FLOOR * 2 / 3
        await am.initialize_app("app")
        assert health.overall_status(health.liveness_checks(ad)) == "pass"


async def test_livez_fails_on_a_hung_initialize_and_names_the_app(clock):
    utility = Utility(MagicMock())
    utility.record_progress()
    release = asyncio.Event()

    async def init():
        await release.wait()

    am, entities = _app_management_with_fake_state(utility, init)
    ad = _make_ad()
    ad.utility, ad.app_management = utility, am
    task = asyncio.create_task(am.initialize_app("app"))
    await asyncio.sleep(0)
    clock.now += FLOOR + 12
    check = health.liveness_checks(ad)["utility:lastProgress"][0]
    assert check["status"] == "fail"
    assert "app 'app' has been initializing since 2026-11-06T10:02:11+00:00" in check["output"]
    release.set()
    await task
    assert health.overall_status(health.liveness_checks(ad)) == "pass"


async def test_initialize_app_records_progress_when_initialize_raises(clock):
    utility = Utility(MagicMock())

    async def init():
        raise RuntimeError("boom")

    am, _ = _app_management_with_fake_state(utility, init)
    with pytest.raises(RuntimeError):
        await am.initialize_app("app")
    assert utility.last_progress == clock.now


async def test_utility_loop_iteration_records_progress(clock):
    ad = MagicMock()
    ad.real_time = False
    ad.stopping = True
    utility = Utility(ad)
    assert utility.last_progress is None
    async with utility._loop_iteration_context():
        pass
    assert utility.last_progress == clock.now


# startup bookkeeping in the real Utility._init_loop


def _utility_for_init_loop(apps_enabled: bool, stopping: bool = False) -> tuple[Utility, MagicMock]:
    ad = MagicMock()
    ad.stopping = stopping
    ad.apps_enabled = apps_enabled
    ad.http = None
    ad.plugins.wait_for_plugins = AsyncMock()
    ad.events.process_event = AsyncMock()
    utility = Utility(ad)
    utility._init_stats = AsyncMock()
    utility._register_services = AsyncMock()
    return utility, ad


async def test_init_loop_startup_completes_only_after_apps_have_started():
    utility, ad = _utility_for_init_loop(apps_enabled=True)
    started, release = asyncio.Event(), asyncio.Event()

    async def start_apps():
        started.set()
        await release.wait()

    ad.app_management.start = start_apps
    assert utility.startup_complete is False
    task = asyncio.create_task(utility._init_loop())
    await started.wait()
    assert utility.startup_complete is False
    assert utility.last_progress is not None  # so a hang in the first boot's initialize() can fail /livez
    release.set()
    await task
    assert utility.startup_complete is True


async def test_init_loop_startup_completes_with_apps_disabled():
    utility, _ = _utility_for_init_loop(apps_enabled=False)
    await utility._init_loop()
    assert utility.startup_complete is True


async def test_init_loop_startup_incomplete_when_stopping_early():
    utility, _ = _utility_for_init_loop(apps_enabled=True, stopping=True)
    await utility._init_loop()
    assert utility.startup_complete is False


# auth


def _failing_ad() -> MagicMock:
    """Every check failing with something to leak: a plugin, a failed app and a stuck one."""
    ad = _make_ad(plugins={"HASS": False}, app_states={"secret_app": "initialize_error"})
    ad.state.state["admin"]["app.slow_app"] = _entity(INITIALIZING)
    ad.utility.last_progress = monotonic() - 1000
    ad.loop = asyncio.get_running_loop()
    ad.executor = None
    return ad


_LEAKS = ("checks", "HASS", "secret_app", "slow_app", "output")
_BAD_CREDENTIALS = [
    pytest.param({}, id="none"),
    pytest.param({"headers": {"x-ad-access": "nope"}}, id="wrong-header"),
    pytest.param({"headers": {"x-ad-access": ""}}, id="empty-header"),
    pytest.param({"headers": {"x-ad-access": "SECRET"}}, id="wrong-case-header"),
    pytest.param({"params": {"api_password": "nope"}}, id="wrong-query"),
    pytest.param({"params": {"api_password": ""}}, id="empty-query"),
    pytest.param({"cookies": {"adcreds": "not-a-hash"}}, id="garbage-cookie"),
    pytest.param({"cookies": {"adcreds": _cookie("nope")}}, id="wrong-cookie"),
    pytest.param({"cookies": {"adcreds": "$2b$31$" + "a" * 53}}, id="high-cost-cookie"),
]
_GOOD_CREDENTIALS = [
    pytest.param({"headers": {"x-ad-access": "secret"}}, id="header"),
    pytest.param({"params": {"api_password": "secret"}}, id="query"),
    pytest.param({"cookies": {"adcreds": _cookie("secret")}}, id="cookie"),
]


@pytest.mark.parametrize("path", ["/livez", "/readyz"])
@pytest.mark.parametrize("kwargs", _BAD_CREDENTIALS)
async def test_failure_detail_hidden_without_valid_credentials(path, kwargs):
    status, _, text = await _get(_make_http(_failing_ad(), password="secret"), path, **kwargs)
    assert status == 503
    assert json.loads(text) == {"status": "fail"}
    assert [leak for leak in _LEAKS if leak in text] == []


@pytest.mark.parametrize("path", ["/livez", "/readyz"])
@pytest.mark.parametrize("kwargs", _GOOD_CREDENTIALS)
async def test_failure_detail_shown_with_valid_credentials(path, kwargs):
    status, body = await _health(_make_http(_failing_ad(), password="secret"), path, **kwargs)
    assert (status, body["status"]) == (503, "fail")
    assert body["checks"]


async def test_stuck_app_named_only_with_credentials(clock):
    ad = _failing_ad()
    ad.utility.last_progress = clock.now - 1000
    http = _make_http(ad, password="secret")
    assert "slow_app" not in (await _get(http, "/livez"))[2]
    assert "app 'slow_app' has been initializing since" in (await _get(http, "/livez", headers={"x-ad-access": "secret"}))[2]


@pytest.mark.parametrize(
    "app_states, expected",
    [({}, "pass"), ({"secret_app": "initialize_error"}, "warn")],
)
async def test_pass_and_warn_detail_hidden_without_credentials(app_states, expected):
    status, text = (await _get(_make_http(_make_ad(app_states=app_states), password="secret"), "/readyz"))[::2]
    assert (status, json.loads(text)) == (200, {"status": expected})
    assert "secret_app" not in text


async def test_detail_shown_to_anyone_without_a_password():
    _, body = await _health(_make_http(_failing_ad()), "/readyz", headers={"x-ad-access": "nope"})
    assert "secret_app" in body["checks"]["apps:failed"][0]["output"]


async def test_header_and_query_secrets_use_constant_time_comparison(monkeypatch):
    compared = []
    real = hmac.compare_digest

    def spy(a, b):
        compared.append((a, b))
        return real(a, b)

    monkeypatch.setattr("appdaemon.http.hmac.compare_digest", spy)
    http = _make_http(_make_ad(), password="secret")
    await _get(http, "/readyz", headers={"x-ad-access": "secret"})
    await _get(http, "/readyz", params={"api_password": "secret"})
    assert compared == [(b"secret", b"secret")] * 2


async def test_high_cost_cookie_is_rejected_without_running_bcrypt(monkeypatch):
    http = _make_http(_make_ad(), password="secret")
    http.work_factor = 12
    checkpw = MagicMock(side_effect=AssertionError("bcrypt must not run"))
    monkeypatch.setattr("appdaemon.http.bcrypt.checkpw", checkpw)
    request = MagicMock(cookies={"adcreds": "$2b$31$" + "a" * 53})
    assert await http.is_authorized(request) is False
    checkpw.assert_not_called()


def _http_with_decorated_handlers() -> HTTP:
    ad = _make_ad()
    ad.loop = asyncio.get_running_loop()
    ad.executor = None
    http = _make_http(ad, password="secret")
    http.valid_tokens = ["tok"]
    http.forcelogon = AsyncMock(return_value=web.Response(status=401, text="logon"))

    async def handler(self, request):
        return web.json_response({"ok": True})

    for path, decorator in {"/securedata": securedata, "/secure": secure, "/route_secure": route_secure}.items():
        http.app.router.add_get(path, functools.partial(decorator(handler), http))
    return http


@pytest.mark.parametrize("path", ["/securedata", "/secure", "/route_secure"])
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"cookies": {"adcreds": "not-a-hash"}}, id="malformed-cookie"),
        pytest.param({"cookies": {"adcreds": _cookie("nope")}}, id="wrong-cookie"),
        pytest.param({"cookies": {"adcreds": "$2b$31$" + "a" * 53}}, id="high-cost-cookie"),
        pytest.param({}, id="no-credentials"),
    ],
)
async def test_decorators_refuse_bad_cookies_without_a_server_error(path, kwargs):
    status, _, _ = await _get(_http_with_decorated_handlers(), path, **kwargs)
    assert status == 401


@pytest.mark.parametrize("path", ["/securedata", "/secure", "/route_secure"])
async def test_decorators_accept_a_valid_cookie(path):
    assert (await _get(_http_with_decorated_handlers(), path, cookies={"adcreds": _cookie("secret")}))[0] == 200


async def test_decorators_keep_their_other_credentials():
    http = _http_with_decorated_handlers()
    assert (await _get(http, "/securedata", headers={"x-ad-access": "secret"}))[0] == 200
    assert (await _get(http, "/route_secure", params={"token": "tok"}))[0] == 200
    assert (await _get(http, "/route_secure", params={"token": "nope"}))[0] == 401
    # The dashboard decorator has only ever honoured the login cookie
    assert (await _get(http, "/secure", headers={"x-ad-access": "secret"}))[0] == 401


async def test_health_routes_win_over_dashboard_catch_all():
    http = _make_http(_make_ad())

    async def dashboard(request):
        return web.json_response({"dashboard": request.match_info["name"]})

    http.app.router.add_get("/{name}", dashboard)
    assert json.loads((await _get(http, "/other"))[2]) == {"dashboard": "other"}
    for path in ("/livez", "/readyz"):
        status, headers, _ = await _get(http, path)
        assert (status, headers["Content-Type"].split(";")[0]) == (200, CONTENT_TYPE)
