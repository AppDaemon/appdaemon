from pydantic import BaseModel

from .common import BoolNum, CoercedPath


class DashboardConfig(BaseModel):
    config_dir: CoercedPath | None = None
    config_file: CoercedPath | None = None

    dashboard_dir: CoercedPath | None = None
    force_compile: BoolNum = False
    compile_on_start: BoolNum = False
    profile_dashboard: bool = False
    dashboard: bool
