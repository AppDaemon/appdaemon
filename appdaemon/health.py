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
FAILED_APP_STATES = {"initialize_error", "compile_error"}


def _check(status: Status, observed: Any, output: str | None = None) -> list[Check]:
    check: Check = {
        "status": status,
        "observedValue": observed,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
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
        if age > timeout:
            output = f"no progress in {age:g}s"
            if ad.app_management.initializing_since:
                name, since = min(ad.app_management.initializing_since.items(), key=lambda item: item[1])
                output += f"; app '{name}' has been initializing since {since.isoformat(timespec='seconds')}"
            else:
                output = f"utility loop has made no progress in {age:g}s"
            check = _check("fail", age, output)
        else:
            check = _check("pass", age)
    check[0]["observedUnit"] = "s"
    return {"utility:lastProgress": check}


def failed_apps(ad: "AppDaemon") -> list[str]:
    return sorted(
        entity_id.removeprefix("app.")
        for entity_id, entity in ad.state.state.get("admin", {}).items()
        if entity_id.startswith("app.") and entity.get("state") in FAILED_APP_STATES
    )


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
        plugin = next(
            (obj["object"] for obj in ad.plugins.plugin_objs.values() if obj["name"] == name),
            None,
        )
        if plugin is None:
            checks[f"plugin:{name}"] = _check("fail", "not loaded", "plugin failed to load")
        elif plugin.is_ready:
            checks[f"plugin:{name}"] = _check("pass", "connected")
        else:
            checks[f"plugin:{name}"] = _check("fail", "disconnected", "plugin is not connected and ready")

    if ad.apps_enabled:
        failed = failed_apps(ad)
        output = f"failed: {', '.join(failed)}" if failed else None
        checks["apps:failed"] = _check("warn" if failed else "pass", len(failed), output)

    return checks
