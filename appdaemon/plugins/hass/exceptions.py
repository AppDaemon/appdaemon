
from dataclasses import dataclass, field

from appdaemon import exceptions as ade


class HAAuthenticationError(Exception):
    pass


class HAEventsSubError(Exception):
    pass


class HAFailedAuthentication(Exception):
    pass


@dataclass
class ScriptNotFound(ade.AppDaemonException):
    script_name: str
    namespace: str
    plugin_name: str
    domain: str = field(init=False, default="script")

    def __str__(self):
        res = f"'{self.script_name}' not found in plugin '{self.plugin_name}'"
        if self.namespace != "default":
            res += f" with namespace '{self.namespace}'"
        return res
