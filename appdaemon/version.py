from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("appdaemon")
except PackageNotFoundError:
    # Fallback for development/editable installs or if package not installed
    __version__ = "unknown"

__version_comments__ = ""
