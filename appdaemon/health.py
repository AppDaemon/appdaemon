"""Liveness and readiness checks, reported in the IETF health check response format.

See https://datatracker.ietf.org/doc/html/draft-inadarei-api-health-check
"""

from datetime import datetime, timezone
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .appdaemon import AppDaemon

Status = Literal["pass", "warn", "fail"]
Check = dict[str, Any]
Checks = dict[str, list[Check]]

CONTENT_TYPE = "application/health+json"
MIN_PROGRESS_TIMEOUT = 300.0
"""Smallest time without progress, in seconds, that counts as wedged"""


def _check(status: Status, observed: Any, output: str | None = None, unit: str | None = None) -> list[Check]:
    check: Check = {"status": status, "observedValue": observed}
    if unit is not None:
        check["observedUnit"] = unit
    check["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if output is not None:
        check["output"] = output
    return [check]


def overall_status(checks: Checks) -> Status:
    statuses = {c["status"] for group in checks.values() for c in group}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def liveness_checks(ad: "AppDaemon") -> Checks:
    """Checks only things a restart would fix, so nothing here may depend on a plugin."""
    utility = ad.utility
    timeout = max(MIN_PROGRESS_TIMEOUT, 10 * ad.config.utility_delay.total_seconds())
    task = getattr(utility, "loop_task", None)

    if task is not None and task.done() and not ad.stopping:
        check = _check("fail", None, "utility loop is not running")
    elif utility.last_progress is None:
        # Still starting up, which can legitimately take a while (e.g. waiting on plugins)
        check = _check("pass", None, "utility loop has not started yet")
    else:
        age = round(monotonic() - utility.last_progress, 1)
        if age <= timeout:
            check = _check("pass", age, unit="s")
        elif stuck := ad.app_management.initializing_apps():
            name, since = stuck[0]
            output = f"no progress in {age:g}s; app '{name}' has been initializing since {since}"
            check = _check("fail", age, output, unit="s")
        else:
            check = _check("fail", age, f"utility loop has made no progress in {age:g}s", unit="s")
    return {"utility:lastProgress": check}


def readiness_checks(ad: "AppDaemon") -> Checks:
    checks: Checks = {}

    if ad.stopping:
        checks["appdaemon:startup"] = _check("fail", False, "AppDaemon is stopping")
    elif ad.utility.startup_complete:
        checks["appdaemon:startup"] = _check("pass", True)
    else:
        checks["appdaemon:startup"] = _check("fail", False, "startup is not complete")

    for name, cfg in ad.plugins.config.items():
        if cfg.disabled:
            continue
        entry = next((obj for obj in ad.plugins.plugin_objs.values() if obj["name"] == name), None)
        if entry is None:
            checks[f"plugin:{name}"] = _check("fail", "not loaded", "plugin failed to load")
        # "active" is cleared by notify_plugin_stopped on any plugin's disconnect; is_ready alone is not (MQTT)
        elif entry["active"] and entry["object"].is_ready:
            checks[f"plugin:{name}"] = _check("pass", "connected")
        else:
            checks[f"plugin:{name}"] = _check("fail", "disconnected", "plugin is not connected and ready")

    if ad.apps_enabled:
        failed = ad.app_management.failed_apps()
        output = f"failed: {', '.join(failed)}" if failed else None
        checks["apps:failed"] = _check("warn" if failed else "pass", len(failed), output)

    return checks
