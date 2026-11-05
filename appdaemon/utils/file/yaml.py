import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("AppDaemon._utility.file.yaml")


def write_yaml_config(path, **kwargs):
    with open(path, "w") as stream:
        yaml.dump(kwargs, stream, Dumper=yaml.SafeDumper)


def read_yaml_config(file: Path) -> dict[str, dict[str, Any]] | None:
    #
    # First locate secrets file
    #
    #    try:
    #
    # Read config file using include directory
    #

    yaml.add_constructor("!include", _include_yaml, Loader=yaml.SafeLoader)

    #
    # Read config file using environment variables
    #

    yaml.add_constructor("!env_var", _env_var_yaml, Loader=yaml.SafeLoader)

    #
    # Initially load file to see if secret directive is present
    #
    yaml.add_constructor("!secret", _dummy_secret, Loader=yaml.SafeLoader)
    with file.open("r") as yamlfd:
        logger.debug("Reading config file: %s", file)
        config = yaml.safe_load(yamlfd)

    # No need to keep processing if the file is empty
    if not bool(config):
        return {}

    if "secrets" in config:
        secrets_file = Path(config["secrets"])
    else:
        secrets_file = file.with_name("secrets.yaml")

    #
    # Read Secrets
    #
    try:
        if secrets_file.exists():
            with secrets_file.open("r") as yamlfd:
                global secrets
                secrets = yaml.safe_load(yamlfd)
    except Exception:
        print(
            "ERROR",
            f"Error loading secrets file: {secrets_file}",
        )
        return None

    #
    # Read config file again, this time with secrets
    #

    yaml.add_constructor("!secret", _secret_yaml, Loader=yaml.SafeLoader)

    with file.open("r") as yamlfd:
        return yaml.safe_load(yamlfd)


def _dummy_secret(loader, node):
    pass


def _secret_yaml(loader, node):
    if secrets is None:
        raise ValueError("!secret used but no secrets file found")

    if node.value not in secrets:
        raise ValueError("{} not found in secrets file".format(node.value))

    return secrets[node.value]


def _env_var_yaml(loader, node):
    env_var = node.value
    if env_var not in os.environ:
        raise ValueError("{} not found in as environment variable".format(env_var))

    return os.environ[env_var]


def _include_yaml(loader, node):
    filename = node.value
    if not os.path.isfile(filename) or filename.split(".")[-1] != "yaml":
        raise ValueError("{} is not a valid yaml file".format(filename))

    with open(filename, "r") as f:
        return yaml.load(f, Loader=yaml.SafeLoader)
