import os
import platform
from collections.abc import Generator
from pathlib import Path
from typing import Any

from appdaemon import exceptions as ade

from .toml import read_toml_config, write_toml_config
from .yaml import read_yaml_config, write_yaml_config

if platform.system() != "Windows":
    import pwd

__all__ = ["read_config_file", "write_config_file", "recursive_get_files", "check_path", "find_path"]


def recursive_get_files(base: Path, suffix: str | set[str], exclude: set[str] | None = None) -> Generator[Path]:
    """Recursively generate file paths.

    Args:
        base (Path): The base directory to start searching from.
        suffix (str): The file extension to filter by.
        exclude (set[str]): A set of directory names to exclude from the search.

    Yields:
        Path objects to files that have the matching extension and are readable.
    """
    suffix = {suffix} if isinstance(suffix, str) else suffix
    exclude = set() if exclude is None else exclude
    for item in base.iterdir():
        if item.name.startswith(".") or (exclude is None or item.name in exclude):
            continue
        elif item.is_file() and item.suffix in suffix and os.access(item, os.R_OK):
            yield item
        elif item.is_dir() and os.access(item, os.R_OK):
            yield from recursive_get_files(item, suffix, exclude)


def read_config_file(file: Path, app_config: bool = False) -> dict[str, dict[str, Any]] | None:
    # raise ValueError
    """Reads a single YAML or TOML file.

    This includes all the mechanics for including secrets and environment variables.

    Args:
        file: Path to the configuration file to read.
        app_config: Flag for whether to add the config_path key to the loaded dictionaries
    """
    try:
        file = Path(file) if not isinstance(file, Path) else file
        match file.suffix.lower():
            case ".yaml" | ".yml":
                full_cfg = read_yaml_config(file)
            case ".toml":
                full_cfg = read_toml_config(file)
            case _:
                raise ValueError(f"ERROR: unknown file extension: {file.suffix}")

        if app_config and full_cfg is not None:
            for key, cfg in full_cfg.items():
                if key == "sequence":
                    for seq_cfg in cfg.values():
                        seq_cfg["config_path"] = file
                elif cfg is not None and isinstance(cfg, dict):
                    cfg["config_path"] = file

        return full_cfg
    except Exception as exc:
        raise ade.ConfigReadFailure(file) from exc


def write_config_file(file: Path, **kwargs):
    """Writes a single YAML or TOML file."""
    file = Path(file) if not isinstance(file, Path) else file
    match file.suffix:
        case ".yaml":
            return write_yaml_config(file, **kwargs)
        case ".toml":
            return write_toml_config(file, **kwargs)
        case _:
            raise ValueError(f"ERROR: unknown file extension: {file.suffix}")


def find_path(name: str) -> Path:
    search_paths = [Path("~/.homeassistant").expanduser(), Path("/etc/appdaemon")]
    for path in search_paths:
        if (file := (path / name)).exists():
            return file
    else:
        raise FileNotFoundError(f"Did not find {name} in {search_paths}")


def check_path(type, logger, inpath, pathtype="directory", permissions=None):  # noqa: C901
    # disable checks for windows platform

    # Some root directories are expected to be owned by people other than the user so skip some checks
    skip_owner_checks = ["/Users", "/home"]

    if platform.system() == "Windows":
        return

    try:
        path = os.path.abspath(inpath)

        perms = permissions
        if pathtype == "file":
            dir = os.path.dirname(path)
            file = path
            if perms is None:
                perms = "r"
        else:
            dir = path
            file = None
            if perms is None:
                perms = "rx"

        dirs = []
        while not os.path.ismount(dir):
            dirs.append(dir)
            d, F = os.path.split(dir)
            dir = d

        fullpath = True
        for directory in reversed(dirs):
            if not os.access(directory, os.F_OK):
                logger.warning("%s: %s does not exist exist", type, directory)
                fullpath = False
            elif not os.path.isdir(directory):
                if os.path.isfile(directory):
                    logger.warning(
                        "%s: %s exists, but is a file instead of a directory",
                        type,
                        directory,
                    )
                    fullpath = False
            else:
                owner = find_owner(directory)
                if "r" in perms and not os.access(directory, os.R_OK):
                    logger.warning(
                        "%s: %s exists, but is not readable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
                if "w" in perms and not os.access(directory, os.W_OK) and directory not in skip_owner_checks:
                    logger.warning(
                        "%s: %s exists, but is not writeable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
                if "x" in perms and not os.access(directory, os.X_OK):
                    logger.warning(
                        "%s: %s exists, but is not executable, owner: %s",
                        type,
                        directory,
                        owner,
                    )
                    fullpath = False
        if fullpath is True:
            owner = find_owner(path)
            user = pwd.getpwuid(os.getuid()).pw_name
            if owner != user:
                logger.warning(
                    "%s: %s is owned by %s but appdaemon is running as %s",
                    type,
                    path,
                    owner,
                    user,
                )

        if file is not None:
            owner = find_owner(file)
            if "r" in perms and not os.access(file, os.R_OK):
                logger.warning("%s: %s exists, but is not readable, owner: %s", type, file, owner)
            if "w" in perms and not os.access(file, os.W_OK):
                logger.warning("%s: %s exists, but is not writeable, owner: %s", type, file, owner)
            if "x" in perms and not os.access(file, os.X_OK):
                logger.warning("%s: %s exists, but is not executable, owner: %s", type, file, owner)
    except KeyError:
        #
        # User ID is not properly set up with a username in docker variants
        # getpwuid() errors out with a KeyError
        # We just have to skip most of these tests
        pass


def find_owner(filename):
    return pwd.getpwuid(os.stat(filename).st_uid).pw_name
