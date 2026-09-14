from datetime import datetime, time, timezone

from app import resolve
from app.extract.merge import merge_candidates
from app.extract.types import Candidate

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
UTC = timezone.utc


def make(**kw):
    base = dict(raw="March 3, 2026, 11:59 PM AoE", date_str="March 3, 2026", time_str="11:59 PM", aoe=True)
    base.update(kw)
    return Candidate(**base)


def test_aoe_to_utc():
    core = resolve.resolve_candidate(make(), NOW, "Asia/Karachi")
    assert core.deadline_utc == datetime(2026, 3, 4, 11, 59, tzinfo=UTC)
    assert core.tz_source == "aoe"


def test_aoe_january():
    c = make(raw="January 15, 2027, 11:59 PM AoE", date_str="January 15, 2027", time_str="11:59 PM")
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.deadline_utc == datetime(2027, 1, 16, 11, 59, tzinfo=UTC)


def test_local_karachi_finalize():
    core = resolve.resolve_candidate(make(), NOW, "Asia/Karachi")
    d = resolve.finalize(core, NOW, "Asia/Karachi")
    assert d.local.iso.hour == 16
    assert d.local.iso.minute == 59
    assert "4:59" in d.local.human
    assert d.epoch_seconds == int(datetime(2026, 3, 4, 11, 59, tzinfo=UTC).timestamp())
    assert d.remaining.expired is True
    assert d.remaining.days == 194


def test_cest_explicit():
    c = make(raw="April 20, 2027, 17:00 CEST", date_str="April 20, 2027", time_str="17:00", aoe=False, tz_hint="CEST")
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.deadline_utc == datetime(2027, 4, 20, 15, 0, tzinfo=UTC)
    assert core.tz_source == "explicit"
    assert core.aoe is False


def test_utc_minus_12_is_aoe():
    c = make(raw="2027-06-01T23:59:59-12:00", date_str="2027-06-01", time_str="23:59:59", tz_hint="-12:00", aoe=False)
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.aoe is True
    assert core.deadline_utc == datetime(2027, 6, 2, 11, 59, 59, tzinfo=UTC)


def test_date_only_default_and_alternates():
    c = make(raw="May 10, 2027", date_str="May 10, 2027", time_str=None, aoe=False, tz_hint=None)
    core = resolve.resolve_candidate(c, NOW, "Asia/Karachi")
    assert core.tz_source == "date_only_default"
    assert core.deadline_utc == datetime(2027, 5, 11, 11, 59, tzinfo=UTC)
    d = resolve.finalize(core, NOW, "Asia/Karachi")
    assert [a.basis for a in d.alternates] == ["utc", "requester_tz"]
    assert d.alternates[0].iso == datetime(2027, 5, 10, 23, 59, tzinfo=UTC)
    assert d.alternates[1].iso == datetime(2027, 5, 10, 18, 59, tzinfo=UTC)
    assert d.note


def test_time_without_tz_fallback():
    c = make(raw="April 20, 2027, 5:00 PM", date_str="April 20, 2027", time_str="5:00 PM", aoe=False, tz_hint=None)
    core = resolve.resolve_candidate(c, NOW, "Asia/Karachi")
    assert core.tz_source == "requester_tz_fallback"
    assert core.deadline_utc == datetime(2027, 4, 20, 12, 0, tzinfo=UTC)
    d = resolve.finalize(core, NOW, "Asia/Karachi")
    assert [a.basis for a in d.alternates] == ["utc", "aoe"]


def test_yearless_future_bump():
    c = make(raw="January 15, 11:59 PM AoE", date_str="January 15", time_str="11:59 PM")
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.deadline_utc == datetime(2027, 1, 16, 11, 59, tzinfo=UTC)


def test_explicit_past_year_stays_past():
    c = make(raw="March 3, 2020, 11:59 PM AoE", date_str="March 3, 2020", time_str="11:59 PM")
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.deadline_utc == datetime(2020, 3, 4, 11, 59, tzinfo=UTC)


def test_relative_tomorrow_5pm():
    c = Candidate(raw="tomorrow at 5pm", date_str=None, time_str="5pm", relative=True, source="llm")
    core = resolve.resolve_candidate(c, NOW, "Asia/Karachi")
    assert core.tz_source == "relative"
    assert core.deadline_utc == datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def test_relative_tomorrow_aoe():
    c = Candidate(raw="tomorrow at 5pm AoE", date_str=None, time_str="5pm", aoe=True, relative=True, source="llm")
    core = resolve.resolve_candidate(c, NOW, "Asia/Karachi")
    assert core.deadline_utc == datetime(2026, 9, 16, 5, 0, tzinfo=UTC)
    assert core.aoe is True


def test_relative_next_friday_aoe():
    c = Candidate(raw="next Friday 11:59pm AoE", date_str=None, time_str="11:59pm", aoe=True, relative=True, source="llm")
    core = resolve.resolve_candidate(c, NOW, "Asia/Karachi")
    assert core.deadline_utc == datetime(2026, 9, 19, 11, 59, tzinfo=UTC)


def test_iana_tz_hint():
    c = make(raw="April 20, 2027, 18:00 Asia/Tokyo", date_str="April 20, 2027", time_str="18:00", aoe=False, tz_hint="Asia/Tokyo")
    core = resolve.resolve_candidate(c, NOW, "UTC")
    assert core.deadline_utc == datetime(2027, 4, 20, 9, 0, tzinfo=UTC)


def test_parse_time_string():
    assert resolve.parse_time_string("11:59 PM") == time(23, 59)
    assert resolve.parse_time_string("23:59") == time(23, 59)
    assert resolve.parse_time_string("5pm") == time(17, 0)
    assert resolve.parse_time_string("5 am") == time(5, 0)
    assert resolve.parse_time_string("12am") == time(0, 0)
    assert resolve.parse_time_string("12pm") == time(12, 0)
    assert resolve.parse_time_string("noon") == time(12, 0)
    assert resolve.parse_time_string("EOD") == time(23, 59)
    assert resolve.parse_time_string("11:59:59 PM") == time(23, 59, 59)
    assert resolve.parse_time_string("5:30 p.m.") == time(17, 30)
    assert resolve.parse_time_string("99:99") is None
    assert resolve.parse_time_string("5") is None
    assert resolve.parse_time_string(None) is None


def test_tz_from_hint():
    tz, aoe = resolve.tz_from_hint("PDT")
    assert tz.utcoffset(None).total_seconds() == -7 * 3600
    assert aoe is False
    tz, _ = resolve.tz_from_hint("UTC+2")
    assert tz.utcoffset(None).total_seconds() == 2 * 3600
    tz, _ = resolve.tz_from_hint("+05:30")
    assert tz.utcoffset(None).total_seconds() == 5.5 * 3600
    tz, aoe = resolve.tz_from_hint("AoE")
    assert aoe is True and tz is resolve.AOE
    tz, aoe = resolve.tz_from_hint("-12:00")
    assert aoe is True
    tz, _ = resolve.tz_from_hint("Asia/Tokyo")
    from zoneinfo import ZoneInfo

    assert tz == ZoneInfo("Asia/Tokyo")
    assert resolve.tz_from_hint("Mars/Phobos") == (None, False)


def test_merge_enriches_rules_from_llm():
    rc = Candidate(raw="June 15, 2026", start=0, end=13, date_str="June 15, 2026")
    lc = Candidate(raw="June 15, 2026. 11:59 PM AoE", start=0, end=31,
                   date_str="June 15, 2026", time_str="11:59 PM", aoe=True, label="Paper deadline", source="llm")
    merged = merge_candidates([rc], [lc])
    assert len(merged) == 1
    assert merged[0].time_str == "11:59 PM"
    assert merged[0].aoe is True
    assert merged[0].label == "Paper deadline"


def test_merge_keeps_disjoint():
    rc = Candidate(raw="June 15, 2026", start=0, end=13, date_str="June 15, 2026")
    lc = Candidate(raw="tomorrow at 5pm", start=40, end=55, relative=True, source="llm")
    merged = merge_candidates([rc], [lc])
    assert len(merged) == 2


def test_remaining_math():
    dl = datetime(2026, 9, 16, 12, 0, 30, tzinfo=UTC)
    r = resolve.remaining(dl, NOW)
    assert r.expired is False
    assert r.total_seconds == 2 * 86400 + 30
    assert (r.days, r.hours, r.minutes, r.seconds) == (2, 0, 0, 30)
    r2 = resolve.remaining(datetime(2026, 9, 12, 12, 0, tzinfo=UTC), NOW)
    assert r2.expired is True and r2.days == 2
