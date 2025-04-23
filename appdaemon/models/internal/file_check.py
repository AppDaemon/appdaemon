from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Any
from collections.abc import Iterable

from pydantic import BaseModel, Field


class FileCheck(BaseModel):
    """Class that keeps track of file changes.

    Usually instantiated with FileCheck.from_paths(...). After instantiation, all the paths are marked as new.

    Call the ``FileCheck.update`` method with a new set of files to compute the changes. Afterwards, paths changed since the last update will be in the relevant new/modified/deleted attribute.

    Attributes:
        mtimes: Mapping of Path objects to the timestamps
        new: Set of new Path objects
        modified: Set of modified Path objects
        deleted: Set of deleted Path objects
    """

    mtimes: dict[Path, float] = Field(default_factory=dict)
    new: set[Path] = Field(default_factory=set)
    modified: set[Path] = Field(default_factory=set)
    deleted: set[Path] = Field(default_factory=set)

    @classmethod
    def from_paths(cls, iter: Iterable[Path]):
        """Use this method to instantiate from Paths"""
        return cls(mtimes={p: p.stat().st_mtime for p in iter})

    def model_post_init(self, __context: Any):
        self.new = set(self.mtimes.keys())

    @property
    def latest(self) -> float:
        try:
            return min(self.mtimes.values())
        except ValueError:
            return 0.0

    @property
    def latest_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.latest)

    @property
    def paths(self) -> Iterable[Path]:
        yield from self.mtimes.keys()

    @property
    def __iter__(self):
        return self.mtimes.__iter__

    @property
    def there_were_changes(self) -> bool:
        """Property that is True if there are any new, modified, or deleted files since the last time the ``FileCheck.update`` method was called"""
        return bool(self.new) or bool(self.modified) or bool(self.deleted)

    def update(self, new_files: Iterable[Path]):
        """Updates the internal new, modified, and deleted sets based on a new set of files"""

        # Convert iterable to a set so that it's easier to check for belonging to it
        new_files = new_files if isinstance(new_files, set) else set(new_files)

        # Reset file sets
        self.new = set()
        self.modified = set()
        self.deleted = set()

        # Check for deleted files
        currently_tracked_files = set(self.mtimes.keys())
        for current_file in currently_tracked_files:
            if current_file not in new_files:
                self.deleted.add(current_file)
                del self.mtimes[current_file]

        # Check new files to see if they're new or modified
        for new_file in new_files:
            new_mtime = new_file.stat().st_mtime

            if mtime := self.mtimes.get(new_file):
                if new_mtime > mtime:
                    self.modified.add(new_file)
            else:
                self.new.add(new_file)

            self.mtimes[new_file] = new_mtime

    def log_changes(self, logger: Logger, app_dir: Path):
        for file in sorted(self.new):
            logger.debug("New app config file: %s", file.relative_to(app_dir.parent))

        for file in sorted(self.modified):
            logger.debug("Detected app config file modification: %s", file.relative_to(app_dir.parent))

        for file in sorted(self.deleted):
            logger.debug("Detected app config file deletion: %s", file.relative_to(app_dir.parent))


class AppConfigFileCheck(FileCheck):
    pass
