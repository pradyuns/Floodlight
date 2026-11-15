"""What the probe observes: launcher rows over time for one typed query."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Kind(Enum):
    APP = "app"
    FILE = "file"
    FOLDER = "folder"
    SETTINGS_PANE = "settings_pane"
    OTHER = "other"


class Source(Enum):
    LOCAL = "local"
    WEB = "web"
    INSTANT = "instant"


@dataclass(frozen=True)
class Row:
    title: str
    kind: Kind
    source: Source
    folder: str | None = None
    pane_id: str | None = None
    selected: bool | None = None
    category: str | None = None  # the launcher's own label for the row, kept for audits


@dataclass(frozen=True)
class Snapshot:
    """Times are milliseconds since the first key was due."""

    read_start_ms: int  # the screen content is no older than this
    read_end_ms: int  # the rows were not known before this
    rows: tuple[Row, ...]
    field_text: str
    primary_action: str | None = None  # the launcher's own Enter label, e.g. Raycast's action bar
    field_mismatch: bool = (
        False  # field showed text other than what was typed; evidence, not scored
    )
    unreadable: str | None = None  # why the read saw nothing; an observation failure, not a result


@dataclass(frozen=True)
class KeyPost:
    planned_ms: int
    actual_ms: int


@dataclass(frozen=True)
class Sample:
    query_id: str
    tool: str
    env: Literal["sparse", "busy"]
    run: int
    condition: Literal["ui_restart", "warm"]
    final_key_post_ms: int  # when the final key was actually posted, not when it was due
    field_shows_ms: int | None
    snapshots: list[Snapshot]
    error: str | None
    attempt: int
    key_posts: tuple[KeyPost, ...]

    @property
    def max_key_lateness_ms(self) -> int:
        return max((k.actual_ms - k.planned_ms for k in self.key_posts), default=0)
