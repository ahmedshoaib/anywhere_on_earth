from .rules import classify_label
from .types import Candidate


def _overlap(a: tuple[int, int], b: tuple[int, int], pad: int = 2) -> bool:
    return a[0] < b[1] + pad and b[0] < a[1] + pad


def merge_candidates(rules_cands: list[Candidate], llm_cands: list[Candidate]) -> list[Candidate]:
    merged = list(rules_cands)
    for lc in llm_cands:
        if lc.start is None or lc.end is None:
            continue
        hit = None
        for rc in merged:
            if rc.start is not None and _overlap((lc.start, lc.end), (rc.start, rc.end)):
                hit = rc
                break
        if hit is None:
            merged.append(lc)
            continue
        if not hit.label and lc.label:
            hit.label = lc.label
            kind = classify_label(lc.label)
            if kind != "other":
                hit.kind = kind
        if not hit.aoe and lc.aoe and not hit.tz_hint:
            hit.aoe = True
        if not hit.tz_hint and lc.tz_hint and not lc.aoe:
            hit.tz_hint = lc.tz_hint
        if not hit.date_str and lc.date_str:
            hit.date_str = lc.date_str
        if not hit.time_str and lc.time_str:
            hit.time_str = lc.time_str
    return merged
