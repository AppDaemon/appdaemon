# Threading

## Configuration

| Property        | Default | Description |
|-----------------|-------------|--------------|
| `pin_apps`      | True  | Whether to pin apps to threads |
| `total_threads` | None  | The total number of threads to create, defaults to the number of active apps. |
| `pin_threads`   | None  | The number (out of the total) of threads to reserve for pinning; only used by `select_q` when `pin_apps=False`. Defaults to all threads |

## Thread Creation

- Threads are created during startup in {py:meth}`~appdaemon.threads.Threading.create_initial_threads`.
- User-configured values are resolved into actual numbers using {py:meth}`~appdaemon.threads.Threading.resolve_thread_counts`.
- Threads all have an ID number (0 - <`appdaemon.total_threads`>)
- Some of them are reserved for pinned callbacks (0 - <`appdaemon.pin_threads`>)
- The remaining are free for unpinned callbacks
- AppDaemon will assign a `pin_thread` to an app when it's created, if `pin_app=True` and `pin_thread=None`.
    - Must be configured in file or have global setting to `pin_app=False` to not get an assigned thread.
- Pin behavior and thread assignments are stored in `ManagedObject` attributes

## Thread Pinning

These settings get passed around through the AppDaemon internals and ultimately determine which thread handles a callback.

| Setting | Description |
|---------|-------------|
| `pin_app`     | Whether the app should be pinned to a single thread. |
| `pin_thread`  | The thread the app is pinned to. This determines which thread the callback gets run in |

| Level | Description |
|-------|--|
| Global        | The global settings are set in the `appdaemon.yaml` file, and each app defaults to the global setting when it's created. |
| Per App       | The pinning behavior for apps can be changed at runtime. The current settings are stored in the corresponding `ManagedObject` |
| Per Callback  | The pinning behavior for a specific callback can be overridden at registration. |

- App gets created by the app manager
    - App object and settings are stored in the `ManagedObject`
    - `pin_app` is set from the config file, defaulting to global setting
    - `pin_thread` could be set from the config file, but could be assigned by AD at that point
- App runs and maybe the `pin_app` or `pin_thread` gets changed at some point.
    - Any changes affect the settings in `ManagedObject`
- Callback could also override either `pin_app` or `pin_thread`
    - `pin_app` should be calculated at callback registration
        - If the *callback* specifies a `pin_thread` that implies `pin_app=True`, otherwise the `pin_thread` will get ignored in `select_q`
        - If `pin_app` ends up being True, but there's no `pin_thread` assigned, one needs to be assigned at call time - will be 0.
        - If `pin_app` is False, `pin_thread` will get ignored at call time
    - Callback lives in internal dicts
        - `pin_app` is never `None`
        - `pin_thread` could be `None` - load distribution should be calculated at call time.
- `pin_app` and `pin_thread` make their way through the internals, eventually to `Threading.select_q`
    - `select_q` hinges on `pin_app` being True/False.
    - `pin_app` is never `None`
    - If `pin_app` is not True, `pin_thread` is ignored, and the thread is automatically chosen according to the load distribution setting

### Config Precedence

1) **Callback-level pin**: Top-level override
2) **App-level pin**: Acts as the default for each callback as it's created.
3) **Config-level pin (default)**: Acts as the default when the app manager creates a new `ManagedObject`

### Default Case

By default, a new thread will be created for each active app, and each app will get pinned to its own thread.

- Default (initial case)
    - Global: `pin_apps=True`
    - App: `pin_app=None`
- Each app has a `ManagedObject` instance that holds the `pin_app` and `pin_thread` settings for that app.
- When an app is created `pin_app=True` gets set (from the global default) and `pin_thread` gets assigned.
- The `pin_app` and `pin_thread` settings for an app can be altered in the `ManagedObject` during runtime.
- The `pin_app` and `pin_thread` settings can be provided during callback registration to override the settings for that callback only.

## Callback Registration

The {py:meth}`~appdaemon.threads.Threading.determine_thread` method is used during callback registration to resolve `pin_app` for that callback.

| Callback Type | Registration | Processing |
|---------------|--------|---------------|
| Schedule      | {py:meth}`~appdaemon.scheduler.Scheduler.insert_schedule` | {py:meth}`~appdaemon.scheduler.Scheduler.exec_schedule`       |
| Event         | {py:meth}`~appdaemon.events.Events.add_event_callback`    | {py:meth}`~appdaemon.events.Events.process_event_callbacks`   |
| State         | {py:meth}`~appdaemon.state.State.add_state_callback`      | {py:meth}`~appdaemon.state.State.process_state_callbacks`     |
| Log           | {py:meth}`~appdaemon.logging.Logging.add_log_callback`    | {py:meth}`~appdaemon.logging.Logging.process_log_callbacks`   |

## Reference

```{eval-rst}
.. autoclass:: appdaemon.threads.Threading
   :members: determine_thread, add_thread, dispatch_worker, select_q, dispatch_worker
```
