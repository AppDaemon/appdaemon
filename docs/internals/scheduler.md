# Scheduler

Anything that depends on a time is handled by the Scheduler. The general idea is that the scheduler will wait do an async wait until the next scheduled event, and if anything happens

## Scheduler Entry Structure

Each entry in the schedule (`self.AD.sched.schedule`) contains the following fields:

| Field         | Type | Description |
|---------------|------|-------------|
| `name`        | `str` | The name of the scheduled callback (usually the method name) |
| `id`          | `str` | Unique identifier for this scheduled entry |
| `callback`    | `functools.partial` | The callback function to be executed, wrapped with bound method |
| `timestamp`   | `datetime.datetime` | The next scheduled execution time (timezone-aware) |
| `interval`    | `datetime.timedelta` | Time interval between repeated executions (0 for one-time callbacks) |
| `basetime`    | `datetime.datetime` | The base time used for calculating subsequent executions |
| `repeat`      | `bool` | Whether this callback should repeat after execution |
| `offset`      | `datetime.timedelta` | Time offset applied to the base time for scheduling |
| `random_start`| `datetime.timedelta \| None` | Start of random time window (if using random scheduling) |
| `random_end`  | `datetime.timedelta \| None` | End of random time window (if using random scheduling) |
| `type`        | `str` | Type of schedule (e.g., 'next_rising', 'interval', 'cron') |
| `pin_app`     | `bool` | Whether to pin this callback to a specific app thread |
| `pin_thread`  | `int` | The thread number to pin this callback to (0 for main thread) |
| `kwargs`      | `dict` | Additional keyword arguments to pass to the callback |

## Reference

```{eval-rst}
.. autoclass:: appdaemon.scheduler.Scheduler
   :members:
```
