import pytest
from appdaemon.models.config.plugin import PluginConfig
from appdaemon.models.internal.app_management import ManagedObject, UpdateMode
from appdaemon.plugin_management import PluginBase

from tests.conftest import ConfiguredAppDaemonFunc

APP_NAME = "hello_world"
ANOTHER_APP = "another_app"
PLUGIN_NS = "default"
OTHER_PLUGIN_NS = "other"


class RegistrationStubPlugin(PluginBase):
    """Minimal plugin so the real registration seam can be exercised without any I/O."""

    async def get_updates(self):
        pass

    async def get_complete_state(self):
        return {}


def plugin_entry(active: bool) -> dict:
    return {
        "object": object(),
        "active": active,
        "name": "test",
    }


def assert_app_running(ad, app_name: str, msg: str) -> None:
    match ad.app_management.objects.get(app_name):
        case ManagedObject(type="app", running=True):
            return
        case _:
            pytest.fail(msg)


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_inactive_plugin_blocks_normal_restart(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """A NORMAL update pass must not restart apps of a plugin marked inactive."""
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs, loggers=["_app_management"]) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        # Simulate plugin failure like notify_plugin_stopped does
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)

        # Mimic PLUGIN_FAILED stopping the app
        stopped = await ad.app_management.stop_app(APP_NAME, delete=True)
        assert stopped, "sanity: app should stop cleanly"
        assert APP_NAME not in ad.app_management.objects

        caplog.clear()

        # NORMAL pass from the utility loop while the plugin is down
        ad.utility.app_update_event.clear()
        await ad.app_management.check_app_updates()

        assert APP_NAME not in ad.app_management.objects, "NORMAL pass should not repopulate init while a plugin is inactive"
        assert "Skipping init repopulation" in caplog.text, "guard branch should log skipping init repopulation"
        assert not any(r.levelname == "ERROR" for r in caplog.records), "no errors expected while guard is active"

        # PLUGIN_RESTART after reconnection starts the app again. Mirror notify_plugin_started,
        # which sets active=True before scheduling PLUGIN_RESTART.
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)
        assert_app_running(ad, APP_NAME, "app should be running after PLUGIN_RESTART")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_plugin_restart_starts_apps(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """After a plugin reconnects, PLUGIN_RESTART must start apps recovered from the stopped-app snapshot.

    A second plugin entry stays inactive the whole time so the init-repopulation guard remains on,
    and the app's ManagedObject was deleted by the failed plugin — only the snapshot can restore it.
    """
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        # The failing plugin and a second, still-inactive plugin
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        ad.plugins.plugin_objs[OTHER_PLUGIN_NS] = {"object": None, "active": False, "name": "other"}

        # PLUGIN_FAILED with the plugin inactive exercises _stop_plugin_apps and the snapshot
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert APP_NAME not in ad.app_management.objects, "sanity: PLUGIN_FAILED should stop the app"
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "sanity: snapshot should be recorded"

        # Simulate reconnection: only the restarted plugin becomes active again, the second
        # plugin stays inactive so the guard remains on and the generic repopulation can't fire
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        assert ad.plugins.any_plugin_inactive(), "sanity: guard should still be on"
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)
        assert_app_running(ad, APP_NAME, "app should be running after PLUGIN_RESTART despite the inactive second plugin")

        # Snapshot for this namespace is consumed on restart
        assert PLUGIN_NS not in ad.app_management.stopped_plugin_apps


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_plugin_restart_isolated_to_namespace(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Restarting one plugin must not start apps snapshotted for a different, still-failed plugin."""
    app_cfgs = {
        APP_NAME: {"module": "hello", "class": "HelloWorld"},
        ANOTHER_APP: {"module": "hello", "class": "HelloWorld"},
    }

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"
        assert ANOTHER_APP in ad.app_management.objects, "sanity: app should start initially"

        # The other plugin failed earlier and stopped another_app; it's still down
        ad.plugins.plugin_objs[OTHER_PLUGIN_NS] = {"object": None, "active": False, "name": "other"}
        stopped = await ad.app_management.stop_app(ANOTHER_APP, delete=True)
        assert stopped, "sanity: app should stop cleanly"
        # Hand-injected because a real PLUGIN_FAILED pass for ns "other" can't be driven here: it
        # requires app objects with that namespace, but apps only get a non-default namespace via
        # set_namespace in their own initialize, which HelloWorld doesn't do. This simulates what
        # notify_plugin_stopped for that plugin would have recorded.
        ad.app_management.stopped_plugin_apps[OTHER_PLUGIN_NS] = {ANOTHER_APP}

        # Now the default plugin fails; drive the real stop path
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert APP_NAME not in ad.app_management.objects, "sanity: PLUGIN_FAILED should stop the app"
        # another_app was already gone, so it must not leak into this namespace's snapshot
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "only directly stopped apps belong to the snapshot"

        # The default plugin reconnects while the other is still inactive
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)

        # Its own snapshot is restored and consumed...
        assert_app_running(ad, APP_NAME, "the restarted plugin's app should be running again")
        assert PLUGIN_NS not in ad.app_management.stopped_plugin_apps

        # ...while the other plugin's snapshotted app stays stopped — no cross-plugin leaks
        assert ANOTHER_APP not in ad.app_management.objects, "app of the still-inactive plugin must not be started"
        assert ad.app_management.stopped_plugin_apps[OTHER_PLUGIN_NS] == {ANOTHER_APP}, "snapshot of the other plugin must be untouched"

        # Other plugin still down, so the guard keeps NORMAL passes from starting its app
        ad.utility.app_update_event.clear()
        await ad.app_management.check_app_updates()
        assert ANOTHER_APP not in ad.app_management.objects, "NORMAL pass must not start the other plugin's app"
        assert ad.app_management.stopped_plugin_apps[OTHER_PLUGIN_NS] == {ANOTHER_APP}, "snapshot of the other plugin must survive the NORMAL pass"


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_plugin_restart_consumes_snapshot(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """A successful PLUGIN_RESTART must pop the namespace's snapshot, whatever it contained."""
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "sanity: snapshot should be recorded"

        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)

        assert_app_running(ad, APP_NAME, "app should be running after PLUGIN_RESTART")
        assert PLUGIN_NS not in ad.app_management.stopped_plugin_apps, "snapshot key should be popped after restart"


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_boot_with_registered_plugin_starts_apps(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """Apps must start on the initial NORMAL load even though a plugin was just registered.

    Two pins against the active=True registration:
    - the registration seam records an entry with "active": True that never counts as inactive
      (with the old active=False this assertion fails),
    - a boot where plugins are registered but not yet started does not block the initial load:
      empty plugin_objs and freshly registered ones alike must let the NORMAL pass start apps.
    """
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        # Pin the registration VALUE via the real seam a never-connected plugin goes through.
        # (Calling the full registration path requires importable plugin modules and an app
        # management entry plus a get_updates task, so the seam method is driven directly with the
        # same arguments the registration loop computes.) The plugin config must exist for
        # active_plugins/config lookups. The ready event is set to mirror a plugin that connected
        # successfully, matching the state the registration loop would see.
        cfg = PluginConfig(name="test", type="dummy")
        ad.plugins.config["test"] = cfg
        plugin = RegistrationStubPlugin(ad, "test", cfg)
        plugin.ready_event.set()
        ad.plugins._register_plugin("test", plugin, PLUGIN_NS)

        match entry := ad.plugins.plugin_objs[PLUGIN_NS]:
            case {"object": PluginBase(), "active": True, "name": "test"}:
                pass
            case _:
                pytest.fail(f"registration must record the plugin as active, got: {entry}")
        assert not ad.plugins.any_plugin_inactive(), "freshly registered plugin must not count as inactive"

        # Boot with no plugins registered yet (plugin_objs empty) doesn't block the initial load
        # either: drive the same NORMAL pass AppManagement.start() uses and pin the guard-off path.
        caplog.clear()
        await ad.app_management.check_app_updates()
        assert not any(
            "Skipping init repopulation" in r.getMessage() for r in caplog.records
        ), "guard must be off during an honest boot with no inactive plugins"
        assert_app_running(ad, APP_NAME, "app must start on the initial NORMAL pass with a registered plugin")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_plugin_failed_twice_merges_snapshot(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """A second PLUGIN_FAILED pass during the same outage must not drop the recorded snapshot."""
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        # First PLUGIN_FAILED pass: the app is still running, so it gets stopped and recorded
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert APP_NAME not in ad.app_management.objects, "sanity: PLUGIN_FAILED should stop the app"
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "sanity: snapshot should be recorded"

        # Second PLUGIN_FAILED pass: the app is already gone, so get_namespace_apps is empty. The
        # snapshot must survive via the setdefault+|= merge, not be overwritten with an empty set.
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "second pass must preserve the snapshot"

        # PLUGIN_RESTART after reconnection still starts it
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)
        assert_app_running(ad, APP_NAME, "app should be running after PLUGIN_RESTART")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_filter_disabled_app(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """PLUGIN_RESTART must skip snapshotted apps whose config is now disabled."""
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        # Plugin fails and the app gets stopped and recorded
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "sanity: snapshot should be recorded"

        # While the plugin is down, someone disables the app's config
        ad.app_management.app_config.root[APP_NAME].disable = True

        # PLUGIN_RESTART must not start the disabled app (pop-time filter) and must not blow up in
        # start_sort on app names whose config is no longer active
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)

        match ad.app_management.objects.get(APP_NAME):
            case ManagedObject(type="app", running=True):
                pytest.fail("disabled app must not be started by PLUGIN_RESTART")
            case _:
                pass

        # Recovery here goes through the init repopulation in check_app_config_files, not the
        # snapshot: the snapshot for this namespace was already popped by the PLUGIN_RESTART above,
        # and the app's ManagedObject is gone, so the not-in-objects repopulation is what adds it
        # back now that the plugin (and thus the guard) is active again
        ad.app_management.app_config.root[APP_NAME].disable = False
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)
        assert_app_running(ad, APP_NAME, "re-enabled app should start on the next PLUGIN_RESTART")


@pytest.mark.ci
@pytest.mark.functional
@pytest.mark.asyncio(loop_scope="session")
async def test_plugin_restart_merges_namespace_apps(configured_appdaemon: ConfiguredAppDaemonFunc) -> None:
    """PLUGIN_RESTART must union apps still present via get_namespace_apps with the snapshot.

    An app re-created while the plugin was down (e.g. created/edited during the outage) has a valid
    ManagedObject again, so get_namespace_apps finds it alongside the snapshot apps; the union must
    start everything without double-starting or raising.
    """
    app_cfgs = {APP_NAME: {"module": "hello", "class": "HelloWorld"}}

    async with configured_appdaemon(app_cfgs=app_cfgs) as (ad, caplog):
        await ad.utility.app_update_event.wait()
        assert APP_NAME in ad.app_management.objects, "sanity: app should start initially"

        # Plugin fails and the app gets stopped and recorded
        ad.plugins.plugin_objs[PLUGIN_NS] = plugin_entry(active=False)
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_FAILED)
        assert APP_NAME not in ad.app_management.objects, "sanity: PLUGIN_FAILED should stop the app"
        assert ad.app_management.stopped_plugin_apps[PLUGIN_NS] == {APP_NAME}, "sanity: snapshot should be recorded"

        # While the plugin is down, the app is re-created out of band (simulating a create/edit
        # during the outage): the ManagedObject exists again but the app isn't started
        assert await ad.app_management.create_app_object(APP_NAME) is not None, "sanity: app object should re-create"
        match ad.app_management.objects.get(APP_NAME):
            case ManagedObject(type="app", running=False):
                pass
            case _:
                pytest.fail("sanity: re-created app should exist but not be running")
        assert ad.app_management.get_namespace_apps(PLUGIN_NS) == {APP_NAME}, "sanity: namespace apps should contain the re-created app"

        # PLUGIN_RESTART with both sources present: snapshot union with get_namespace_apps
        ad.plugins.plugin_objs[PLUGIN_NS]["active"] = True
        await ad.app_management.check_app_updates(plugin_ns=PLUGIN_NS, mode=UpdateMode.PLUGIN_RESTART)

        assert_app_running(ad, APP_NAME, "app must be running after the union restart, exactly once")
        assert not any(
            "Cannot start app" in r.getMessage() for r in caplog.records
        ), "the union must not attempt to double-start the app"
        assert PLUGIN_NS not in ad.app_management.stopped_plugin_apps, "snapshot should be consumed despite the union"
