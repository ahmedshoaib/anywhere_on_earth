import re

from .types import Candidate

MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

DATE_CORE = (
    rf"(?:{MONTH}\.?,?\s+\d{{1,2}}(?:st|nd|rd|th)?(?!\d)(?:\s*,?\s*\d{{4}})?"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?(?!\d)\s+(?:of\s+)?{MONTH}\.?(?:\s*,?\s*\d{{4}})?"
    rf"|\d{{4}}-\d{{1,2}}-\d{{1,2}}"
    rf"|\d{{1,2}}/\d{{1,2}}/\d{{2,4}})"
)

TIME_CORE = (
    r"(?:(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?\s*(?P<ampm>[APap]\.?[Mm]\.?)?"
    r"|(?P<h2>\d{1,2})\s*(?P<ampm2>[APap]\.?[Mm]\.?))"
)

TZ_TOKEN = (
    r"(?:Anywhere\s+on\s+Earth"
    r"|AoE"
    r"|(?:UTC|GMT)[ ]?[+-]\d{1,2}(?::\d{2})?"
    r"|UTC|GMT"
    r"|CEST|CEDT|CET|EEST|EET|WEST|WET|BST|MSK"
    r"|SGT|HKT|JST|KST|PKT|IST"
    r"|AEDT|AEST|NZDT|NZST"
    r"|EDT|EST|CDT|CST|MDT|MST|PDT|PST|AKDT|AKST|HST)"
)

SEP_D_T = r"[\s,]*(?:at|@|on|by)?[\s,]*"
SEP_T_D = r"[\s,]*(?:of|on|by|before)?[\s,]*"

ISO_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:[Tt ](?P<time>\d{2}:\d{2}(?::\d{2})?)[ ]?(?P<tz>Z|[+-]\d{2}:?\d{2})?)?"
)
REVERSE_RE = re.compile(
    rf"(?P<time>{TIME_CORE})[ ]*(?P<tz>\b{TZ_TOKEN}\b)?{SEP_T_D}(?P<date>{DATE_CORE})",
    re.IGNORECASE,
)
FORWARD_RE = re.compile(
    rf"(?P<date>{DATE_CORE})(?:{SEP_D_T}(?P<time>{TIME_CORE})[ ]*(?P<tz>\b{TZ_TOKEN}\b)?)?",
    re.IGNORECASE,
)
_PEEK_TZ_RE = re.compile(
    rf"[ ]?,?[ ]*(?:\([ ]*)?(?P<tz>\b{TZ_TOKEN}\b)", re.IGNORECASE
)

_IS_AOE_RE = re.compile(r"(?i)^(?:aoe|anywhere\s+on\s+earth|(?:utc|gmt)?[ ]?-12(?::?00)?)$")

_LABEL_SEP_RE = re.compile(r"([A-Za-z][A-Za-z0-9 \-/&()']{2,48}?)\s*(?::|\u2014|\u2013|\s[-\u2013\u2014]\s)\s*$")
_LABEL_DUE_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9 \-/&()']{2,48}?)\s+(?:is\s+|are\s+)?(?:due|deadline|closes?)\s*$",
    re.IGNORECASE,
)

KIND_KEYWORDS = (
    ("abstract", "abstract_deadline"),
    ("camera", "camera_ready"),
    ("notification", "notification"),
    ("decision", "notification"),
    ("accept", "notification"),
    ("rebuttal", "rebuttal"),
    ("author response", "rebuttal"),
    ("deadline", "deadline"),
    ("due", "deadline"),
    ("submi", "deadline"),
    ("closes", "deadline"),
)


def classify_label(label: str) -> str:
    low = label.lower()
    for kw, kind in KIND_KEYWORDS:
        if kw in low:
            return kind
    return "other"


def infer_label(text: str, pos: int) -> tuple[str | None, str]:
    window = text[max(0, pos - 80):pos]
    window = re.split(r"[\n\r]+", window)[-1]
    window = window.lstrip("*\u2022- #\t ")
    m = _LABEL_SEP_RE.search(window)
    from_due = False
    if m is None:
        m = _LABEL_DUE_RE.search(window)
        from_due = m is not None
    if m is not None:
        label = m.group(1).strip(" \t,.;:")
        if label:
            kind = classify_label(label)
            if from_due and kind == "other":
                kind = "deadline"
            return label, kind
    low = window.lower()
    for kw, kind in KIND_KEYWORDS:
        if kw in low:
            return None, kind
    return None, "other"


def _norm_ampm(a: str) -> str:
    return re.sub(r"[.\s]", "", a).upper()


def _time_str_from(m: re.Match) -> str | None:
    if m.group("h") is not None:
        s = f"{m.group('h')}:{m.group('m')}"
        if m.group("s") is not None:
            s += f":{m.group('s')}"
        if m.group("ampm") is not None:
            s += " " + _norm_ampm(m.group("ampm"))
        return s
    if m.group("h2") is not None:
        return f"{m.group('h2')} {_norm_ampm(m.group('ampm2'))}"
    return None


def _tz_fields(tz_raw: str | None) -> tuple[bool, str | None]:
    if not tz_raw:
        return False, None
    norm = " ".join(tz_raw.split())
    if _IS_AOE_RE.match(norm):
        return True, None
    if norm.upper() == "Z":
        return False, "UTC"
    return False, norm


def _candidate_from_match(m: re.Match, text: str, flavor: str) -> Candidate | None:
    start = m.start()
    end = m.end()
    date_s = m.group("date")
    time_s = m.group("time") if flavor == "iso" else _time_str_from(m)
    tz_s = m.group("tz")
    if flavor != "iso" and tz_s is None:
        peek = _PEEK_TZ_RE.match(text, end)
        if peek is not None:
            tz_s = peek.group("tz")
            end = peek.end()
    aoe, tz_hint = _tz_fields(tz_s)
    label, kind = infer_label(text, start)
    raw = text[start:end].strip()
    return Candidate(
        raw=raw,
        start=start,
        end=end,
        date_str=date_s,
        time_str=time_s,
        aoe=aoe,
        tz_hint=tz_hint,
        relative=False,
        label=label,
        kind=kind,
        source="rules",
    )


def _overlaps_any(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    return any(span[0] < t[1] and t[0] < span[1] for t in taken)


def find_candidates(text: str) -> list[Candidate]:
    out: list[Candidate] = []
    taken: list[tuple[int, int]] = []
    for rx, flavor in ((ISO_RE, "iso"), (REVERSE_RE, "rev"), (FORWARD_RE, "fwd")):
        for m in rx.finditer(text):
            cand = _candidate_from_match(m, text, flavor)
            if cand is None:
                continue
            span = (cand.start, cand.end)
            if _overlaps_any(span, taken):
                continue
            out.append(cand)
            taken.append(span)
    out.sort(key=lambda c: (c.start is None, c.start))
    return out
