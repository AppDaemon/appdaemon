"""Tests for the /livez and /readyz health endpoints."""

import asyncio
import functools
import json
from datetime import datetime, timedelta, timezone
from time import monotonic
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from appdaemon import health, utility_loop
from appdaemon.app_management import AppManagement
from appdaemon.http import HTTP, securedata
from appdaemon.models.config import MainConfig
from appdaemon.utility_loop import Utility

pytestmark = [
    pytest.mark.ci,
    pytest.mark.unit,
    pytest.mark.asyncio,
]


def _plugin(name: str, ready: bool) -> dict:
    return {"name": name, "object": MagicMock(is_ready=ready)}


def _make_ad(plugins: dict[str, bool] | None = None, app_states: dict[str, str] | None = None) -> MagicMock:
    plugins = {"HASS": True} if plugins is None else plugins
    ad = MagicMock()
    ad.stopping = False
    ad.apps_enabled = True
    ad.config.utility_delay = timedelta(seconds=1)
    ad.utility.last_progress = monotonic()
    ad.utility.startup_complete = True
    ad.utility.loop_task.done.return_value = False
    ad.app_management.initializing_since = {}
    ad.plugins.config = {name: MagicMock(disabled=False) for name in plugins}
    ad.plugins.plugin_objs = {f"ns_{name}": _plugin(name, ready) for name, ready in plugins.items()}
    ad.state.state = {
        "admin": {f"app.{n}": {"state": s} for n, s in (app_states or {}).items()}
        | {"sensor.active_apps": {"state": 1}}
    }
    ad.config_dir = None
    return ad


def _make_http(ad: MagicMock, password: str | None = None, **extra) -> HTTP:
    http_cfg = {"url": "http://127.0.0.1:5050"} | ({"password": password} if password else {})
    ad_cfg = {"latitude": 0, "longitude": 0, "elevation": 0, "time_zone": "UTC", "config_dir": ".", "config_file": "appdaemon.yaml"}
    main_cfg = MainConfig.model_validate({"appdaemon": ad_cfg, "http": http_cfg} | extra)
    http = HTTP(ad, main_cfg)
    ad.http = http
    return http


async def _get(http: HTTP, path: str, **kwargs):
    async with TestClient(TestServer(http.app)) as client:
        resp = await client.get(path, **kwargs)
        return resp.status, resp.content_type, await resp.json(content_type=None)


async def test_readyz_pass():
    http = _make_http(_make_ad(app_states={"a": "idle"}))
    status, content_type, body = await _get(http, "/readyz")
    assert status == 200
    assert content_type == "application/health+json"
    assert body["status"] == "pass"
    assert body["checks"]["plugin:HASS"][0]["status"] == "pass"
    assert body["checks"]["apps:failed"][0]["observedValue"] == 0


async def test_readyz_warn_on_failed_app():
    ad = _make_ad(app_states={"good": "idle", "bad": "initialize_error", "worse": "compile_error"})
    status, _, body = await _get(_make_http(ad), "/readyz")
    assert status == 200
    assert body["status"] == "warn"
    check = body["checks"]["apps:failed"][0]
    assert (check["status"], check["observedValue"]) == ("warn", 2)
    assert "bad" in check["output"]


async def test_readyz_fail_on_disconnected_plugin():
    status, _, body = await _get(_make_http(_make_ad(plugins={"HASS": False, "MQTT": True})), "/readyz")
    assert status == 503
    assert body["status"] == "fail"
    assert body["checks"]["plugin:HASS"][0]["status"] == "fail"
    assert body["checks"]["plugin:MQTT"][0]["status"] == "pass"


async def test_readyz_fail_on_plugin_that_never_loaded():
    ad = _make_ad()
    ad.plugins.plugin_objs = {}
    status, _, body = await _get(_make_http(ad), "/readyz")
    assert status == 503
    assert body["checks"]["plugin:HASS"][0]["observedValue"] == "not loaded"


async def test_readyz_skips_disabled_plugin():
    ad = _make_ad(plugins={"HASS": True})
    ad.plugins.config["OFF"] = MagicMock(disabled=True)
    _, _, body = await _get(_make_http(ad), "/readyz")
    assert "plugin:OFF" not in body["checks"]


async def test_readyz_fail_before_startup_complete():
    ad = _make_ad()
    ad.utility.startup_complete = False
    status, _, body = await _get(_make_http(ad), "/readyz")
    assert status == 503
    assert body["checks"]["appdaemon:startup"][0]["status"] == "fail"


async def test_readyz_fail_while_stopping():
    ad = _make_ad()
    ad.stopping = True
    status, _, _ = await _get(_make_http(ad), "/readyz")
    assert status == 503


async def test_livez_pass():
    status, content_type, body = await _get(_make_http(_make_ad()), "/livez")
    assert status == 200
    assert content_type == "application/health+json"
    assert body["status"] == "pass"
    assert body["checks"]["utility:lastProgress"][0]["status"] == "pass"


async def test_livez_fail_on_stale_loop():
    ad = _make_ad()
    ad.utility.last_progress = monotonic() - health.MIN_PROGRESS_TIMEOUT - 5
    status, _, body = await _get(_make_http(ad), "/livez")
    assert status == 503
    assert body["status"] == "fail"


async def test_livez_fail_when_loop_task_died():
    ad = _make_ad()
    ad.utility.loop_task.done.return_value = True
    status, _, _ = await _get(_make_http(ad), "/livez")
    assert status == 503


async def test_livez_pass_before_first_tick():
    ad = _make_ad()
    ad.utility.last_progress = None
    status, _, _ = await _get(_make_http(ad), "/livez")
    assert status == 200


async def test_livez_ignores_disconnected_plugin_and_failed_apps():
    ad = _make_ad(plugins={"HASS": False}, app_states={"bad": "initialize_error"})
    status, _, body = await _get(_make_http(ad), "/livez")
    assert status == 200
    assert set(body["checks"]) == {"utility:lastProgress"}


@pytest.mark.parametrize("path", ["/livez", "/readyz"])
async def test_detail_hidden_without_credentials(path):
    http = _make_http(_make_ad(), password="secret")
    status, _, body = await _get(http, path)
    assert status == 200
    assert body == {"status": "pass"}


def _failing_ad() -> MagicMock:
    """Every check failing with something to leak: a plugin, a failed app and a stuck one."""
    ad = _make_ad(plugins={"HASS": False}, app_states={"secret_app": "initialize_error"})
    ad.utility.last_progress = monotonic() - 1000
    ad.app_management.initializing_since = {"slow_app": datetime.now(timezone.utc)}
    ad.loop = asyncio.get_running_loop()
    ad.executor = None
    return ad


def _cookie(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


async def _get_raw(http: HTTP, path: str, **kwargs) -> tuple[int, str]:
    async with TestClient(TestServer(http.app)) as client:
        resp = await client.get(path, **kwargs)
        return resp.status, await resp.text()


_LEAKS = ("checks", "HASS", "secret_app", "slow_app", "output")


@pytest.mark.parametrize("path", ["/livez", "/readyz"])
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="none"),
        pytest.param({"headers": {"x-ad-access": "nope"}}, id="wrong-header"),
        pytest.param({"headers": {"x-ad-access": ""}}, id="empty-header"),
        pytest.param({"headers": {"x-ad-access": "SECRET"}}, id="wrong-case-header"),
        pytest.param({"params": {"api_password": "nope"}}, id="wrong-query"),
        pytest.param({"params": {"api_password": ""}}, id="empty-query"),
        pytest.param({"cookies": {"adcreds": "not-a-hash"}}, id="garbage-cookie"),
        pytest.param({"cookies": {"adcreds": _cookie("nope")}}, id="wrong-cookie"),
    ],
)
async def test_failure_detail_hidden_without_valid_credentials(path, kwargs):
    status, text = await _get_raw(_make_http(_failing_ad(), password="secret"), path, **kwargs)
    assert status == 503
    assert json.loads(text) == {"status": "fail"}
    assert [leak for leak in _LEAKS if leak in text] == []


async def test_warn_detail_hidden_without_credentials():
    ad = _make_ad(app_states={"secret_app": "initialize_error"})
    status, text = await _get_raw(_make_http(ad, password="secret"), "/readyz")
    assert (status, json.loads(text)) == (200, {"status": "warn"})
    assert "secret_app" not in text


@pytest.mark.parametrize("path", ["/livez", "/readyz"])
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"headers": {"x-ad-access": "secret"}}, id="header"),
        pytest.param({"params": {"api_password": "secret"}}, id="query"),
        pytest.param({"cookies": {"adcreds": _cookie("secret")}}, id="cookie"),
    ],
)
async def test_failure_detail_shown_with_valid_credentials(path, kwargs):
    status, _, body = await _get(_make_http(_failing_ad(), password="secret"), path, **kwargs)
    assert (status, body["status"]) == (503, "fail")
    assert body["checks"]


async def test_stuck_app_named_only_with_credentials():
    http = _make_http(_failing_ad(), password="secret")
    _, text = await _get_raw(http, "/livez", headers={"x-ad-access": "secret"})
    assert "app 'slow_app' has been initializing since" in text


async def test_detail_shown_to_anyone_without_a_password():
    _, _, body = await _get(_make_http(_failing_ad()), "/readyz", headers={"x-ad-access": "nope"})
    assert "secret_app" in body["checks"]["apps:failed"][0]["output"]


async def test_wrong_cookie_is_unauthorized_on_the_api():
    """It used to fall through ``securedata`` and return None instead of a response."""
    http = _make_http(_failing_ad(), password="secret")

    @securedata
    async def handler(self, request):
        return web.json_response({"ok": True})

    http.app.router.add_get("/secured", functools.partial(handler, http))
    assert (await _get_raw(http, "/secured", cookies={"adcreds": _cookie("nope")}))[0] == 401
    assert (await _get_raw(http, "/secured", cookies={"adcreds": "not-a-hash"}))[0] == 401
    assert (await _get_raw(http, "/secured", cookies={"adcreds": _cookie("secret")}))[0] == 200


async def test_health_routes_win_over_dashboard_catch_all():
    http = _make_http(_make_ad())
    # The dashboard catch-all is registered after the http routes when dashboards are enabled
    async def dashboard(request):
        return web.json_response({"dashboard": request.match_info["name"]})

    http.app.router.add_get("/{name}", dashboard)
    assert (await _get(http, "/other"))[2] == {"dashboard": "other"}
    for path in ("/livez", "/readyz"):
        status, content_type, _ = await _get(http, path)
        assert (status, content_type) == (200, "application/health+json")


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


def _real_app_management(utility: Utility, init) -> AppManagement:
    ad = MagicMock()
    ad.utility = utility
    am = AppManagement(ad)
    am.objects["app"] = MagicMock(object=MagicMock(initialize=init))
    am.set_state = AsyncMock()
    am.app_module_rel_path = MagicMock()
    return am


async def test_livez_pass_during_long_reload_while_apps_keep_initializing(clock):
    utility = Utility(MagicMock())
    utility.record_progress()

    async def init():
        pass

    am = _real_app_management(utility, init)
    ad = _make_ad()
    ad.utility, ad.app_management = utility, am
    # A reload of many slow apps blocks the loop well past the threshold overall
    for _ in range(5):
        clock.now += health.MIN_PROGRESS_TIMEOUT / 2
        await am.initialize_app("app")
        assert health.overall_status(health.liveness_checks(ad)) == "pass"
    assert clock.now - 1000 > health.MIN_PROGRESS_TIMEOUT


async def test_livez_fail_on_hung_initialize_names_app(clock):
    utility = Utility(MagicMock())
    utility.record_progress()
    release = asyncio.Event()

    async def init():
        await release.wait()

    am = _real_app_management(utility, init)
    ad = _make_ad()
    ad.utility, ad.app_management = utility, am
    task = asyncio.create_task(am.initialize_app("app"))
    await asyncio.sleep(0)
    clock.now += health.MIN_PROGRESS_TIMEOUT + 12
    check = health.liveness_checks(ad)["utility:lastProgress"][0]
    assert check["status"] == "fail"
    assert check["observedValue"] == health.MIN_PROGRESS_TIMEOUT + 12
    assert "app 'app' has been initializing since" in check["output"]
    release.set()
    await task
    assert health.overall_status(health.liveness_checks(ad)) == "pass"


async def test_livez_stall_without_initializing_app_says_so(clock):
    ad = _make_ad()
    ad.utility.last_progress = clock.now - health.MIN_PROGRESS_TIMEOUT - 1
    output = health.liveness_checks(ad)["utility:lastProgress"][0]["output"]
    assert output == f"utility loop has made no progress in {health.MIN_PROGRESS_TIMEOUT + 1:g}s"


async def test_initialize_app_records_progress_when_initialize_raises(clock):
    utility = Utility(MagicMock())

    async def init():
        raise RuntimeError("boom")

    am = _real_app_management(utility, init)
    with pytest.raises(RuntimeError):
        await am.initialize_app("app")
    assert utility.last_progress == clock.now
    assert am.initializing_since == {}


async def test_utility_loop_iteration_records_tick():
    ad = MagicMock()
    ad.real_time = False
    ad.stopping = True
    utility = Utility(ad)
    assert utility.last_progress is None
    async with utility._loop_iteration_context():
        pass
    assert utility.last_progress is not None
