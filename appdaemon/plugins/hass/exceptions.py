from dataclasses import dataclass, field


from appdaemon import exceptions as ade


@dataclass
class HAConnectionFailure(ade.AppDaemonException):
    def __str__(self):
        return "Connection to Home Assistant failed"


@dataclass
class HAAuthenticationError(ade.AppDaemonException):
    pass


@dataclass
class HAEventsSubError(ade.AppDaemonException):
    code: int
    msg: str

    def __str__(self) -> str:
        return f"{self.code}: {self.msg}"


@dataclass
class HAFailedAuthentication(ade.AppDaemonException):
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

@dataclass
class HassConnectionError(ade.AppDaemonException):
    msg: str

    def __str__(self) -> str:
        return self.msg
