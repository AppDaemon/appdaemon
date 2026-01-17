"""Type aliases and protocols used throughout AppDaemon."""

from datetime import timedelta

# Type alias for values that can be parsed to timedelta
TimeDeltaLike = str | int | float | timedelta
