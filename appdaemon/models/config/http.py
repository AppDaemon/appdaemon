from typing import Literal

from pydantic import BaseModel, HttpUrl, SecretStr

from .common import CoercedPath


class HTTPConfig(BaseModel, extra="allow"):
    url: HttpUrl | None = None
    password: SecretStr | None = None
    transport: Literal["ws", "socketio"] = "ws"
    ssl_certificate: CoercedPath | None = None
    ssl_key: CoercedPath | None = None
    static_dirs: dict[str, CoercedPath] | None = None
    headers: dict[str, str] | None = None
