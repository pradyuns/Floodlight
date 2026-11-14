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
    t_ms: int  # milliseconds since the first key was posted
    rows: tuple[Row, ...]
    field_text: str
    primary_action: str | None = None  # the launcher's own Enter label, e.g. Raycast's action bar


@dataclass(frozen=True)
class Sample:
    query_id: str
    tool: str
    env: Literal["sparse", "busy"]
    run: int
    condition: Literal["ui_restart", "warm"]
    final_key_post_ms: int
    field_shows_ms: int | None
    snapshots: list[Snapshot]
    error: str | None
    attempt: int
