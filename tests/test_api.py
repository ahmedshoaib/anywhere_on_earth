from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEXT = (
    "Important dates:\n"
    "Abstract deadline: January 15, 2027, 11:59 PM AoE\n"
    "Full paper deadline: March 3, 2027, 23:59 AoE\n"
    "Notification: April 20, 2027, 5:00 PM CEST\n"
    "Camera-ready due: May 10, 2027\n"
    "Workshop proposals due 2027-06-01T23:59:59-12:00"
)

EXPECTED_UTC = [
    datetime(2027, 1, 16, 11, 59, tzinfo=timezone.utc),
    datetime(2027, 3, 4, 11, 59, tzinfo=timezone.utc),
    datetime(2027, 4, 20, 15, 0, tzinfo=timezone.utc),
    datetime(2027, 5, 11, 11, 59, tzinfo=timezone.utc),
    datetime(2027, 6, 2, 11, 59, 59, tzinfo=timezone.utc),
]


def to_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_extract_full(client):
    r = client.post("/api/extract", json={"text": TEXT, "tz": "Asia/Karachi"})
    assert r.status_code == 200
    data = r.json()
    assert data["degraded"] is True
    assert data["requester_tz"] == "Asia/Karachi"
    dls = data["deadlines"]
    assert len(dls) == 5
    got = [to_dt(d["deadline_utc"]) for d in dls]
    assert got == EXPECTED_UTC
    first = dls[0]
    assert first["aoe"] is True
    assert first["kind"] == "abstract_deadline"
    assert first["epoch_seconds"] == int(EXPECTED_UTC[0].timestamp())
    assert first["local"]["tz"] == "Asia/Karachi"
    assert to_dt(first["local"]["iso"]).hour == 16
    assert first["remaining"]["expired"] is False
    assert first["remaining"]["days"] > 0
    assert first["source"] == "rules"


def test_extract_date_only_alternates(client):
    r = client.post("/api/extract", json={"text": "Camera-ready due: May 10, 2027", "tz": "Asia/Karachi"})
    d = r.json()["deadlines"][0]
    assert d["tz_source"] == "date_only_default"
    assert [a["basis"] for a in d["alternates"]] == ["utc", "requester_tz"]
    assert to_dt(d["alternates"][0]["iso"]) == datetime(2027, 5, 10, 23, 59, tzinfo=timezone.utc)
    assert to_dt(d["alternates"][1]["iso"]) == datetime(2027, 5, 10, 18, 59, tzinfo=timezone.utc)
    assert d["note"]


def test_extract_time_without_tz(client):
    r = client.post("/api/extract", json={"text": "Submissions close April 20, 2027, 5:00 PM", "tz": "Asia/Karachi"})
    d = r.json()["deadlines"][0]
    assert d["tz_source"] == "requester_tz_fallback"
    assert to_dt(d["deadline_utc"]) == datetime(2027, 4, 20, 12, 0, tzinfo=timezone.utc)
    assert [a["basis"] for a in d["alternates"]] == ["utc", "aoe"]


def test_extract_header_tz(client):
    r = client.post("/api/extract", json={"text": "due March 3, 2027, 23:59 AoE"}, headers={"X-Timezone": "America/New_York"})
    data = r.json()
    d = data["deadlines"][0]
    assert data["requester_tz"] == "America/New_York"
    assert to_dt(d["local"]["iso"]) == EXPECTED_UTC[1].astimezone(ZoneInfo("America/New_York"))
    assert "EST" in d["local"]["human"] or "EDT" in d["local"]["human"]


def test_extract_expired(client):
    r = client.post("/api/extract", json={"text": "deadline was March 3, 2020, 11:59 PM AoE"})
    d = r.json()["deadlines"][0]
    assert d["remaining"]["expired"] is True
    assert d["remaining"]["total_seconds"] < 0


def test_extract_no_dates(client):
    r = client.post("/api/extract", json={"text": "nothing to see here"})
    assert r.json()["deadlines"] == []


def test_invalid_tz(client):
    r = client.post("/api/extract", json={"text": "due March 3, 2027", "tz": "Mars/Phobos"})
    assert r.status_code == 400


def test_empty_text_rejected(client):
    r = client.post("/api/extract", json={"text": ""})
    assert r.status_code == 422


def test_too_long_text(client):
    from app import config

    r = client.post("/api/extract", json={"text": "x" * (config.MAX_TEXT_CHARS + 1)})
    assert r.status_code == 413


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["degraded"] is True
    assert data["model_loaded"] is False


def test_now(client):
    r = client.get("/api/now", params={"tz": "Asia/Karachi"})
    assert r.status_code == 200
    assert r.json()["tz"] == "Asia/Karachi"
    assert "human" in r.json()["local"]


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "AoE Deadline" in r.text
