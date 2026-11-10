"""Demo-site behaviour (raise-the-dead spec, Requirement 8)."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as demo

STATIC = Path(demo.__file__).parent / "static"
AUTH = {"Authorization": f"Bearer {demo.DEMO_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DEMO_FRONTEND", raising=False)
    monkeypatch.delenv("NECROPOLIS_VERIFICATION_TOKEN", raising=False)
    return TestClient(demo.app)


def test_v1_user_is_open_and_fake(client):          # the zombie: Req 8.2
    r = client.get("/api/v1/users/1")
    assert r.status_code == 200
    body = r.json()
    assert body["_fake"] is True and "email" in body["data"]


def test_v2_user_needs_token(client):               # the guarded sibling: Req 8.2
    r = client.get("/api/v2/users/1")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/v2/users/1", headers=AUTH).status_code == 200


def test_session_token_flow(client):
    token = client.post("/api/v2/session").json()["token"]
    assert client.get("/api/v2/orders", headers={"Authorization": f"Bearer {token}"}).status_code == 200


@pytest.mark.parametrize("path,status", [
    ("/api/v1/orders", 401), ("/api/v1/status", 200), ("/api/v1/debug/trace", 500),
    ("/api/v1/legacy-export", 410), ("/api/v2/orders", 401), ("/api/v1/users/999", 404),
])
def test_status_codes(client, path, status):
    assert client.get(path).status_code == status


def test_head_matches_get(client):
    for path in ("/api/v1/users/1", "/api/v2/users/1", "/api/v1/legacy-export", "/"):
        assert client.head(path).status_code == client.get(path).status_code


def test_debug_trace_is_marked_fake(client):
    text = client.get("/api/v1/debug/trace").text
    assert "Traceback (most recent call last)" in text and "FAKE DEMO ERROR" in text


def test_every_json_body_is_marked_fake(client):     # Req 8.2
    for path in ("/api/v1/users/1", "/api/v1/status", "/api/v1/legacy-export"):
        assert client.get(path).json()["_fake"] is True
    assert client.get("/api/v2/users/2", headers=AUTH).json()["_fake"] is True
    assert client.post("/api/v2/session").json()["_fake"] is True


def test_fake_people_use_reserved_values():
    for u in demo.USERS.values():
        assert u["email"].endswith("@example.com")
        assert re.fullmatch(r"\+1-555-01\d\d", u["phone"])   # 555-0100..0199 is reserved for fiction


def test_frontend_switch(client, monkeypatch):       # Req 8.1
    assert "app.v1.js" in client.get("/").text
    monkeypatch.setenv("DEMO_FRONTEND", "v2")
    page = client.get("/").text
    assert "app.v2.js" in page and "/api/v1/" not in page


def test_v2_front_end_never_references_v1():         # the zombie must be missing from the current front end
    for f in ("index.v2.html", "app.v2.js"):
        assert "/api/v1/" not in (STATIC / f).read_text()


def test_v1_front_end_references_v1_api():           # so the archive's JS holds the v1 paths
    js = (STATIC / "app.v1.js").read_text()
    for p in ("`/api/v1/users/${id}`", '"/api/v1/orders"', '"/api/v1/status"', '"/api/v1/legacy-export"'):
        assert p in js


def test_wellknown_token_from_env_only(client, monkeypatch):
    assert client.get("/.well-known/necropolis-verification.txt").status_code == 404
    monkeypatch.setenv("NECROPOLIS_VERIFICATION_TOKEN", "abc123")
    assert client.get("/.well-known/necropolis-verification.txt").text == "abc123"


def test_no_api_docs_exposed(client):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404


def test_demo_header(client):
    assert "fake" in client.get("/api/v1/status").headers["x-demo-site"]
