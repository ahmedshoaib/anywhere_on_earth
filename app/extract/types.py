from dataclasses import dataclass


@dataclass
class Candidate:
    raw: str
    start: int | None = None
    end: int | None = None
    date_str: str | None = None
    time_str: str | None = None
    aoe: bool = False
    tz_hint: str | None = None
    relative: bool = False
    label: str | None = None
    kind: str = "other"
    source: str = "rules"
