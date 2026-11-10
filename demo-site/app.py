"""Lantern Lane: a fictional demo shop that Zombie API Necropolis probes in its demo.

Everything here is invented. The shop, the people and the orders are fake, and every JSON body carries
`"_fake": true`. Deploy it only on a domain you own.

The zombie story:
  * Front end v1 (DEMO_FRONTEND=v1) calls the v1 API. Archive it first with Save Page Now.
  * Then switch to DEMO_FRONTEND=v2. The front end now calls only the v2 API, but the v1 API keeps answering.
    That is the zombie Necropolis finds.

Endpoints:
  /api/v1/users/{id}      200, fake user incl. email/phone, NO auth      -> the zombie (Rampaging)
  /api/v1/orders          401                                              -> guarded (Stirring)
  /api/v1/status          200 {"status": "ok"}                             -> alive, no risk (Risen)
  /api/v1/debug/trace     500, fake Python traceback                       -> verbose error + debug path
  /api/v1/legacy-export   410 Gone                                         -> already buried
  /api/v2/session  POST   returns the fake demo token
  /api/v2/users/{id}      401 without the token                            -> the guarded sibling
  /api/v2/orders          401 without the token
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
STATIC = HERE / "static"
DEMO_TOKEN = "FAKE-DEMO-TOKEN-NOT-A-SECRET"  # deliberately public: this is a demo login, not a credential
GET_HEAD = ["GET", "HEAD"]

USERS = {
    1: {"name": "Casper Example", "email": "casper@example.com", "phone": "+1-555-0101",
        "address": "1 Hollow Lane, Exampleville"},
    2: {"name": "Wanda Placeholder", "email": "wanda@example.com", "phone": "+1-555-0102",
        "address": "13 Crypt Row, Exampleville"},
    3: {"name": "Morty Fictional", "email": "morty@example.com", "phone": "+1-555-0103",
        "address": "7 Lantern Lane, Exampleville"},
}
ORDERS = [
    {"id": 1001, "user_id": 1, "item": "Pumpkin lantern", "total": 12.5},
    {"id": 1002, "user_id": 2, "item": "Fog machine", "total": 49.0},
    {"id": 1003, "user_id": 3, "item": "Bone-white candles (x6)", "total": 9.75},
]
FAKE_TRACE = """Traceback (most recent call last):
  File "/srv/lantern/app/legacy.py", line 88, in export_all
    rows = db.execute(QUERY_ALL_USERS).fetchall()
  File "/srv/lantern/app/db.py", line 41, in execute
    return self._conn.execute(sql)
sqlite3.OperationalError: no such table: users_v1
(FAKE DEMO ERROR: this stack trace is invented for the Necropolis demo)
"""

app = FastAPI(title="Lantern Lane (fictional demo shop)", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def frontend() -> str:
    """Which front end to serve. Read on every request so the switch needs no code change."""
    v = os.environ.get("DEMO_FRONTEND", "v1").strip().lower()
    return v if v in ("v1", "v2") else "v1"


def fake(data: dict | list) -> dict:
    return {"_fake": True, "data": data}


def require_token(authorization: str | None) -> None:
    if authorization != f"Bearer {DEMO_TOKEN}":
        raise HTTPException(status_code=401, detail="authentication required",
                            headers={"WWW-Authenticate": "Bearer"})


# ---------- pages ----------

@app.api_route("/", methods=GET_HEAD)
def index() -> FileResponse:
    return FileResponse(STATIC / f"index.{frontend()}.html", media_type="text/html")


@app.api_route("/robots.txt", methods=GET_HEAD)
def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nAllow: /\n")


@app.api_route("/.well-known/necropolis-verification.txt", methods=GET_HEAD)
def necropolis_verification() -> PlainTextResponse:
    """File-based ownership proof for Necropolis. The token comes from the environment only."""
    token = os.environ.get("NECROPOLIS_VERIFICATION_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404)
    return PlainTextResponse(token)


# ---------- v1 API: removed from the v2 front end, still running ----------

@app.api_route("/api/v1/users/{user_id}", methods=GET_HEAD)
def v1_user(user_id: int) -> dict:
    user = USERS.get(user_id)
    if user is None:
        raise HTTPException(status_code=404)
    return fake({"id": user_id, **user})          # no auth check: the bug the demo is about


@app.api_route("/api/v1/orders", methods=GET_HEAD)
def v1_orders() -> dict:
    raise HTTPException(status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Basic"})


@app.api_route("/api/v1/status", methods=GET_HEAD)
def v1_status() -> dict:
    return {"_fake": True, "status": "ok"}


@app.api_route("/api/v1/debug/trace", methods=GET_HEAD)
def v1_debug_trace() -> PlainTextResponse:
    return PlainTextResponse(FAKE_TRACE, status_code=500)


@app.api_route("/api/v1/legacy-export", methods=GET_HEAD)
def v1_legacy_export() -> JSONResponse:
    return JSONResponse({"_fake": True, "error": "gone", "detail": "legacy export was retired"}, status_code=410)


# ---------- v2 API: what the current front end uses ----------

@app.post("/api/v2/session")
def v2_session() -> dict:
    return {"_fake": True, "token": DEMO_TOKEN, "note": "demo login for a fictional shop"}


@app.api_route("/api/v2/users/{user_id}", methods=GET_HEAD)
def v2_user(user_id: int, authorization: str | None = Header(default=None)) -> dict:
    require_token(authorization)
    user = USERS.get(user_id)
    if user is None:
        raise HTTPException(status_code=404)
    return fake({"id": user_id, "name": user["name"]})


@app.api_route("/api/v2/orders", methods=GET_HEAD)
def v2_orders(authorization: str | None = Header(default=None)) -> dict:
    require_token(authorization)
    return fake(ORDERS)


@app.middleware("http")
async def demo_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Demo-Site"] = "fictional; all data is fake"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
