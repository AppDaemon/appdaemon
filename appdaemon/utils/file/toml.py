import logging
import os
import re
from pathlib import Path
from typing import Any

import tomli
import tomli_w

logger = logging.getLogger("AppDaemon._utility.file.toml")


def write_toml_config(path, **kwargs):
    with open(path, "wb") as stream:
        tomli_w.dump(kwargs, stream)


def read_toml_config(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("rb") as f:
        config = tomli.load(f)

    # now figure out secrets file

    if "secrets" in config:
        secrets_file = Path(config["secrets"])
    else:
        secrets_file = path.with_name("secrets.toml")

    try:
        with secrets_file.open("rb") as f:
            secrets = tomli.load(f)
    except FileNotFoundError:
        # We have no secrets
        secrets = None

    # traverse config looking for !secret and !env

    final_config = toml_sub(config, secrets, os.environ)
    return final_config


def toml_sub(data, secrets, env):
    result = None

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = toml_sub(value, secrets, env)

        assert id(result) != id(data)

    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(toml_sub(item, secrets, env))

        assert id(result) != id(data)

    elif isinstance(data, tuple):
        aux = []
        for item in data:
            aux.append(toml_sub(item, secrets, env))
        result = tuple(aux)

        assert id(result) != id(data)

    else:
        result = data
        if isinstance(data, str):
            r = re.match(r"^!secret\s+(\w+)$", data)
            if r is not None:
                key = r.group(1)
                if secrets is None:
                    print(f"ERROR: !secret used and no secrets file: '{data}'")
                elif key in secrets:
                    result = secrets[key]
                else:
                    print(f"ERROR: !secret ({key}) not found in secrets file")

            r = re.search(r"^!env\s+(\w+)$", data)
            if r is not None:
                key = r.group(1)
                if key in env:
                    result = env[key]
                else:
                    print(f"ERROR: !env ({key}) not found in environment")

    return result
