from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import dateparser
from dateutil import parser as dateutil_parser

from .extract.types import Candidate
from .schema import Alternate, Deadline, Localized, Remaining

UTC = timezone.utc
AOE = timezone(timedelta(hours=-12), "AoE")

TZ_ABBREV_MINUTES = {
    "HST": -600, "AKST": -540, "AKDT": -480,
    "PST": -480, "PDT": -420, "MST": -420, "MDT": -360,
    "CST": -360, "CDT": -300, "EST": -300, "EDT": -240,
    "PKT": 300, "IST": 330, "SGT": 480, "HKT": 480, "JST": 540, "KST": 540,
    "MSK": 180, "BST": 60, "WET": 0, "WEST": 60, "CET": 60, "CEST": 120,
    "EET": 120, "EEST": 180, "AEST": 600, "AEDT": 660, "NZST": 720, "NZDT": 780,
    "UTC": 0, "GMT": 0, "Z": 0, "UT": 0,
}

_OFFSET_RX = re.compile(r"(?i)^(?:UTC|GMT)?[ ]?([+-])(\d{1,2})(?::?(\d{2}))?$")
_TIME_RX = re.compile(r"(?i)^\s*(?:(\d{1,2}):(\d{2})(?::(\d{2}))?|(\d{1,2}))\s*([ap])?\.?\s*m?\.?\s*$")
_TZ_STRIP_RX = re.compile(
    r"(?i)\s*\b(?:anywhere\s+on\s+earth|aoe|"
    r"(?:utc|gmt)[ ]?[+-]\d{1,2}(?::\d{2})?|utc|gmt|"
    + "|".join(TZ_ABBREV_MINUTES)
    + r")\b\s*$"
)
_RELATIVE_RX = re.compile(
    r"(?i)\b(tomorrow|today|tonight|yesterday|next\s+\w+|this\s+\w+|coming\s+\w+|"
    r"in\s+\d+\s+(?:day|week|month|year)s?|\d+\s+(?:day|week|month)s?\s+(?:from\s+now|later))\b"
)
_HAS_YEAR_RX = re.compile(r"\d{4}|(?<!\d)\d{1,2}/\d{1,2}/\d{2}(?!\d)")
_BAD_TZNAME_RX = re.compile(r"[+-]\d{2}:?\d{2}")
_TIME_IN_PHRASE_RX = re.compile(
    r"(?i)\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\b|\b\d{1,2}\s*[ap]\.?m\.?\b"
)
_TZ_ANY_RX = re.compile(
    r"(?i)\b(?:anywhere\s+on\s+earth|aoe|"
    r"(?:utc|gmt)[ ]?[+-]\d{1,2}(?::\d{2})?|utc|gmt|"
    + "|".join(TZ_ABBREV_MINUTES)
    + r")\b"
)
_NEXT_WD_RX = re.compile(
    r"(?i)\b(?:next|this|coming|upcoming)\s+(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b"
)


def valid_tz(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def tz_from_hint(hint: str | None) -> tuple[tzinfo | None, bool]:
    if not hint:
        return None, False
    h = " ".join(hint.split())
    hu = h.upper().replace("_", " ")
    if hu in ("AOE", "ANYWHERE ON EARTH"):
        return AOE, True
    m = _OFFSET_RX.match(hu)
    if m is not None:
        sign = -1 if m.group(1) == "-" else 1
        tz = timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
        return tz, tz.utcoffset(None) == -timedelta(hours=12)
    if hu in TZ_ABBREV_MINUTES:
        return timezone(timedelta(minutes=TZ_ABBREV_MINUTES[hu])), False
    z = valid_tz(h.strip())
    if z is not None:
        return z, False
    return None, False


def parse_time_string(s: str | None) -> time | None:
    if not s:
        return None
    s = s.strip()
    low = s.lower()
    if re.fullmatch(r"e\.?o\.?d\.?|end\s+of\s+day", low):
        return time(23, 59)
    if low == "noon":
        return time(12, 0)
    if low in ("midnight", "mid-night"):
        return time(0, 0)
    m = _TIME_RX.match(s)
    if m is None:
        s2 = _TZ_STRIP_RX.sub("", s).strip()
        if s2 and s2 != s:
            return parse_time_string(s2)
        return None
    if m.group(4) is not None and m.group(5) is None:
        return None
    h = int(m.group(1) or m.group(4))
    mi = int(m.group(2) or 0)
    sec = int(m.group(3) or 0)
    ap = (m.group(5) or "").lower()
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "p" else 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59 and 0 <= sec <= 59):
        return None
    return time(h, mi, sec)


def parse_date_string(s: str | None, base: datetime) -> tuple[date | None, time | None]:
    if not s:
        return None, None
    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": base.replace(tzinfo=None),
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    d = dateparser.parse(s, languages=["en"], settings=settings)
    if d is None:
        for dayfirst in (False, True):
            try:
                d = dateutil_parser.parse(s, default=base, dayfirst=dayfirst)
                break
            except (ValueError, OverflowError):
                d = None
        if d is not None and not _HAS_YEAR_RX.search(s) and d.date() < base.date():
            try:
                d = d.replace(year=d.year + 1)
            except ValueError:
                d = d.replace(year=d.year + 1, day=28)
    if d is None or not (1990 <= d.year <= 2100):
        return None, None
    tod = d.time() if d.time() != time(0, 0) else None
    return d.date(), tod


@dataclass
class ResolvedCore:
    raw_text: str
    label: str | None
    kind: str
    aoe: bool
    tz_source: str
    source: str
    deadline_utc: datetime
    date_val: date
    time_val: time
    alt_specs: list[tuple[str, tzinfo | None, time]]
    note: str | None


def resolve_candidate(c: Candidate, now_utc: datetime, requester_tz_name: str) -> ResolvedCore | None:
    requester_tz = ZoneInfo(requester_tz_name)
    base = now_utc.astimezone(requester_tz)

    if c.relative or (c.date_str is None and _RELATIVE_RX.search(c.raw)):
        return _resolve_relative(c, base, requester_tz)

    date_str = (c.date_str or "").strip() or c.raw
    date_val, tod_from_date = parse_date_string(date_str, base)
    if date_val is None:
        return None
    time_val = parse_time_string(c.time_str)
    if time_val is None:
        time_val = tod_from_date

    hint_tz, hint_is_aoe = tz_from_hint(c.tz_hint)
    aoe_flag = c.aoe or hint_is_aoe

    common = dict(
        raw_text=c.raw.strip(),
        label=c.label,
        kind=c.kind,
        aoe=aoe_flag,
        source=c.source,
        date_val=date_val,
        time_val=time(23, 59) if time_val is None else time_val,
    )

    if aoe_flag or hint_tz is not None:
        tz = AOE if aoe_flag else hint_tz
        deadline = datetime.combine(common["date_val"], common["time_val"], tzinfo=tz).astimezone(UTC)
        note = None
        if time_val is None:
            note = (
                "No time given - assuming 23:59 Anywhere on Earth (UTC-12)."
                if aoe_flag
                else "No time given - assuming end of day in the stated timezone."
            )
        return ResolvedCore(
            deadline_utc=deadline, tz_source="aoe" if aoe_flag else "explicit",
            alt_specs=[], note=note, **common
        )

    if time_val is not None:
        deadline = datetime.combine(date_val, time_val, tzinfo=requester_tz).astimezone(UTC)
        return ResolvedCore(
            deadline_utc=deadline, tz_source="requester_tz_fallback",
            alt_specs=[("utc", UTC, time_val), ("aoe", AOE, time_val)],
            note="Time given without a timezone - assumed to be in your timezone; alternatives below.",
            **common
        )

    tod = time(23, 59)
    deadline = datetime.combine(date_val, tod, tzinfo=AOE).astimezone(UTC)
    return ResolvedCore(
        deadline_utc=deadline, tz_source="date_only_default",
        alt_specs=[("utc", UTC, tod), ("requester_tz", None, tod)],
        note="No time or timezone given - primary assumes 23:59 Anywhere on Earth (UTC-12); alternatives below.",
        **common
    )


def _resolve_relative(c: Candidate, base: datetime, requester_tz: ZoneInfo) -> ResolvedCore | None:
    settings = {
        "RELATIVE_BASE": base.replace(tzinfo=None),
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    phrase = " ".join(_TZ_ANY_RX.sub(" ", c.raw).split())
    phrase = _NEXT_WD_RX.sub(r"\1", phrase)
    if not phrase:
        phrase = c.raw
    dt = None
    for cand_text in (phrase, c.raw, c.date_str or ""):
        if not cand_text:
            continue
        dt = dateparser.parse(cand_text, languages=["en"], settings=settings)
        if dt is None:
            date_only = " ".join(_TIME_IN_PHRASE_RX.sub(" ", cand_text).split())
            if date_only and date_only != cand_text:
                dt = dateparser.parse(date_only, languages=["en"], settings=settings)
        if dt is not None:
            break
    if dt is None:
        return None
    t = parse_time_string(c.time_str)
    if t is None:
        m = _TIME_IN_PHRASE_RX.search(c.raw)
        t = parse_time_string(m.group(0)) if m else None
    if t is None:
        t = time(23, 59)
    hint_tz, hint_is_aoe = tz_from_hint(c.tz_hint)
    tz = AOE if (c.aoe or hint_is_aoe) else (hint_tz or requester_tz)
    if c.aoe or hint_is_aoe or hint_tz is not None:
        note = "Relative date - the clock time is applied in the stated timezone."
    else:
        note = "Relative date - interpreted in your timezone as of now."
    deadline = datetime.combine(dt.date(), t, tzinfo=tz).astimezone(UTC)
    return ResolvedCore(
        raw_text=c.raw.strip(), label=c.label, kind=c.kind, aoe=c.aoe or hint_is_aoe,
        tz_source="relative", source=c.source, deadline_utc=deadline, date_val=dt.date(),
        time_val=t, alt_specs=[], note=note,
    )


def _tz_label(dt: datetime) -> str:
    name = dt.tzname() or ""
    if _BAD_TZNAME_RX.fullmatch(name):
        name = getattr(dt.tzinfo, "key", None) or "UTC"
    return name or "UTC"


def humanize(dt: datetime, tz: tzinfo) -> str:
    local = dt.astimezone(tz)
    h12 = local.strftime("%I").lstrip("0") or "12"
    ap = local.strftime("%p").lower()
    return f"{local.strftime('%a, %b %d, %Y')} \u00b7 {h12}:{local.strftime('%M')} {ap} {_tz_label(local)}"


def remaining(deadline: datetime, now_utc: datetime) -> Remaining:
    total = int((deadline - now_utc).total_seconds())
    expired = total < 0
    a = abs(total)
    days, rem = divmod(a, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if expired:
        human = f"{days}d {hours}h {minutes}m ago" if days else (f"{hours}h {minutes}m ago" if hours else f"{minutes}m ago")
    else:
        human = f"{days}d {hours}h {minutes}m" if days else (f"{hours}h {minutes}m" if hours else f"{minutes}m")
    return Remaining(
        expired=expired, total_seconds=total, days=days, hours=hours,
        minutes=minutes, seconds=seconds, human=human,
    )


def finalize(core: ResolvedCore, now_utc: datetime, requester_tz_name: str) -> Deadline:
    tz = ZoneInfo(requester_tz_name)
    local_dt = core.deadline_utc.astimezone(tz)
    alternates = []
    for basis, alt_tz, tod in core.alt_specs:
        z = tz if alt_tz is None else alt_tz
        adt = datetime.combine(core.date_val, tod, tzinfo=z).astimezone(UTC)
        alternates.append(Alternate(basis=basis, iso=adt, human=humanize(adt, z)))
    return Deadline(
        raw_text=core.raw_text,
        label=core.label,
        kind=core.kind,
        aoe=core.aoe,
        tz_source=core.tz_source,
        source=core.source,
        deadline_utc=core.deadline_utc,
        epoch_seconds=int(core.deadline_utc.timestamp()),
        local=Localized(tz=requester_tz_name, iso=local_dt, human=humanize(local_dt, tz)),
        alternates=alternates,
        note=core.note,
        remaining=remaining(core.deadline_utc, now_utc),
    )
