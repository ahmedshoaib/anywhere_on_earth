from app.extract import rules


def find_all(text):
    return rules.find_candidates(text)


def find_one(text):
    cands = rules.find_candidates(text)
    assert len(cands) == 1, [c.raw for c in cands]
    return cands[0]


def test_forward_aoe():
    c = find_one("Full paper deadline: March 3, 2026, 11:59 PM AoE")
    assert c.date_str == "March 3, 2026"
    assert c.time_str == "11:59 PM"
    assert c.aoe is True
    assert c.tz_hint is None
    assert c.kind == "deadline"
    assert c.label == "Full paper deadline"


def test_forward_24h_aoe():
    c = find_one("Full paper deadline March 3, 2026 23:59 AoE")
    assert c.time_str == "23:59"
    assert c.aoe is True


def test_anywhere_on_earth_words():
    c = find_one("due January 15, 2027, 11:59 p.m. Anywhere on Earth")
    assert c.aoe is True
    assert c.kind == "deadline"


def test_reverse_aoe():
    c = find_one("Deadline 11:59 PM AoE, March 3, 2026")
    assert c.date_str == "March 3, 2026"
    assert c.time_str == "11:59 PM"
    assert c.aoe is True


def test_reverse_on():
    c = find_one("The system closes at 23:59 AoE on 15 March 2026")
    assert c.aoe is True
    assert c.date_str == "15 March 2026"


def test_explicit_cest():
    c = find_one("Camera-ready: 20 April 2026, 17:00 CEST")
    assert c.tz_hint == "CEST"
    assert c.aoe is False
    assert c.kind == "camera_ready"
    assert c.label == "Camera-ready"


def test_explicit_utc_offset():
    c = find_one("Notification: April 20, 2027, 5:00 PM UTC+2")
    assert c.tz_hint == "UTC+2"


def test_date_only():
    c = find_one("Due March 3, 2026")
    assert c.time_str is None
    assert c.aoe is False
    assert c.tz_hint is None
    assert c.kind == "deadline"


def test_date_only_with_trailing_aoe():
    c = find_one("Papers due May 10, 2027 AoE")
    assert c.aoe is True
    assert c.time_str is None


def test_iso_with_aoe_offset():
    c = find_one("Workshop proposals due 2027-06-01T23:59:59-12:00")
    assert c.aoe is True
    assert c.time_str == "23:59:59"
    assert c.date_str == "2027-06-01"


def test_iso_z():
    c = find_one("Hard deadline 2026-03-03T23:59Z")
    assert c.tz_hint == "UTC"
    assert c.time_str == "23:59"


def test_iso_bare_date():
    c = find_one("due 2027-06-01")
    assert c.time_str is None
    assert c.tz_hint is None


def test_no_dates():
    assert find_all("No dates in here at all, just words.") == []


def test_month_year_is_not_day():
    cands = find_all("Submissions open May 2026 and close June 15, 2026.")
    assert [c.raw for c in cands] == ["June 15, 2026"]


def test_multiple_and_kinds():
    text = (
        "Important dates:\n"
        "Abstract deadline: January 15, 2027, 11:59 PM AoE\n"
        "Full paper deadline: March 3, 2027, 23:59 AoE\n"
        "Notification: April 20, 2027, 5:00 PM CEST\n"
        "Camera-ready due: May 10, 2027\n"
        "Workshop proposals due 2027-06-01T23:59:59-12:00"
    )
    cands = find_all(text)
    assert len(cands) == 5
    kinds = [c.kind for c in cands]
    assert kinds == ["abstract_deadline", "deadline", "notification", "camera_ready", "deadline"]
    assert all(c.aoe for c in (cands[0], cands[1], cands[4]))


def test_label_due_phrase():
    c = find_one("Abstract submissions are due March 3, 2026, 11:59 PM AoE")
    assert c.label == "Abstract submissions"
    assert c.kind == "abstract_deadline"


def test_ordinal_suffix():
    c = find_one("Rebuttal period ends March 3rd, 2026 at 5pm PDT")
    assert c.date_str == "March 3rd, 2026"
    assert c.time_str == "5 PM"
    assert c.tz_hint == "PDT"
