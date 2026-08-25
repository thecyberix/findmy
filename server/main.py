"""Find Me web API: Apple ID sign-in via FindMy.py plus a local demo mode."""

from __future__ import annotations

import secrets
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.apple import (
    accessory_from_json_text,
    accessory_name,
    create_account,
    describe_2fa_methods,
    fetch_locations,
    findmy_available,
    load_2fa_methods,
    login,
    persist_accessory,
    request_2fa,
    submit_2fa,
)
from server.demo_data import DEMO_ACCESSORIES
from server.persistence import EncryptedStore

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DATA = ROOT / "data"
LIBS = DATA / "ani_libs.bin"
DATA.mkdir(exist_ok=True)
STORE = EncryptedStore(DATA / "session.enc", DATA / "session.key")

COOKIE = "findme_session"
sessions: dict[str, dict[str, Any]] = {}

app = FastAPI(title="Find Me", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:43147", "http://localhost:43147"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginBody(BaseModel):
    email: str
    password: str = Field(min_length=1)


class TwoFactorBody(BaseModel):
    index: int
    code: str | None = None


def session_id(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def require_session(request: Request) -> dict[str, Any]:
    sid = session_id(request)
    if not sid or sid not in sessions:
        raise HTTPException(401, "Sign in first.")
    return sessions[sid]


def set_cookie(response: Response, sid: str) -> None:
    response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 12)


def save_session(sess: dict[str, Any]) -> None:
    account = sess.get("account")
    if sess.get("mode") != "live" or account is None or sess.get("pending_2fa"):
        return
    accessories = [
        {key: value for key, value in item.items() if key != "account"}
        for item in sess.get("accessories", [])
    ]
    STORE.save({"account": account.to_json(), "accessories": accessories})


def restore_session(response: Response) -> dict[str, Any]:
    saved = STORE.load()
    if not saved or not saved.get("account"):
        raise HTTPException(404, "No saved Apple session.")
    try:
        from findmy import AppleAccount

        account = AppleAccount.from_json(saved["account"], anisette_libs_path=LIBS)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Saved Apple session could not be restored: {exc}") from exc
    sid = secrets.token_hex(16)
    sessions[sid] = {
        "mode": "live",
        "email": account.account_name or "",
        "first_name": account.first_name or "",
        "last_name": account.last_name or "",
        "account": account,
        "accessories": saved.get("accessories", []),
        "pending_2fa": False,
        "methods": [],
    }
    set_cookie(response, sid)
    return sessions[sid]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "findmy": findmy_available()}


@app.post("/api/auth/demo")
def auth_demo(response: Response) -> dict[str, Any]:
    sid = secrets.token_hex(16)
    sessions[sid] = {
        "mode": "demo",
        "email": "demo@icloud.example",
        "first_name": "Demo",
        "last_name": "Account",
        "account": None,
        "accessories": [dict(item) for item in DEMO_ACCESSORIES],
        "pending_2fa": False,
    }
    set_cookie(response, sid)
    return {"ok": True, "mode": "demo"}


@app.post("/api/auth/login")
def auth_login(body: LoginBody, response: Response) -> dict[str, Any]:
    if not findmy_available():
        raise HTTPException(
            503,
            "FindMy.py is not installed. Use demo mode, or pip install -r requirements.txt.",
        )
    sid = secrets.token_hex(16)
    try:
        account = create_account(LIBS)
        state, needs_2fa, logged_in = login(account, body.email.strip(), body.password)
    except Exception as exc:  # noqa: BLE001 — surface Apple/library errors
        raise HTTPException(400, f"Apple sign-in failed: {exc}") from exc

    sessions[sid] = {
        "mode": "live",
        "email": body.email.strip(),
        "first_name": getattr(account, "first_name", None) or "",
        "last_name": getattr(account, "last_name", None) or "",
        "account": account,
        "accessories": [],
        "pending_2fa": needs_2fa,
        "login_state": str(state),
        "methods": load_2fa_methods(account) if needs_2fa else [],
    }
    if logged_in:
        save_session(sessions[sid])
    set_cookie(response, sid)
    methods = describe_2fa_methods(sessions[sid]["methods"]) if needs_2fa else []
    return {
        "ok": True,
        "mode": "live",
        "needs_2fa": needs_2fa,
        "logged_in": logged_in,
        "methods": methods,
    }


@app.post("/api/auth/resume")
def auth_resume(response: Response) -> dict[str, Any]:
    sess = restore_session(response)
    return {"ok": True, "mode": sess["mode"]}


@app.get("/api/auth/2fa-methods")
def auth_methods(request: Request) -> dict[str, Any]:
    sess = require_session(request)
    if sess["mode"] != "live" or sess["account"] is None:
        raise HTTPException(400, "Apple sign-in is required for 2FA.")
    try:
        if not sess.get("methods"):
            sess["methods"] = load_2fa_methods(sess["account"])
        methods = describe_2fa_methods(sess["methods"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return {"methods": methods}


@app.post("/api/auth/2fa/request")
def auth_2fa_request(body: TwoFactorBody, request: Request) -> dict[str, Any]:
    sess = require_session(request)
    if sess["account"] is None:
        raise HTTPException(400, "Apple sign-in is required for 2FA.")
    try:
        if not sess.get("methods"):
            sess["methods"] = load_2fa_methods(sess["account"])
        request_2fa(sess["methods"], body.index)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Could not send a code: {exc}") from exc
    return {"ok": True}


@app.post("/api/auth/2fa/submit")
def auth_2fa_submit(body: TwoFactorBody, request: Request) -> dict[str, Any]:
    sess = require_session(request)
    if sess["account"] is None:
        raise HTTPException(400, "Apple sign-in is required for 2FA.")
    if not body.code:
        raise HTTPException(400, "Enter the 2FA code.")
    try:
        if not sess.get("methods"):
            sess["methods"] = load_2fa_methods(sess["account"])
        submit_2fa(sess["methods"], body.index, body.code.strip())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"2FA failed: {exc}") from exc
    sess["pending_2fa"] = False
    sess["first_name"] = getattr(sess["account"], "first_name", None) or sess["first_name"]
    sess["last_name"] = getattr(sess["account"], "last_name", None) or sess["last_name"]
    save_session(sess)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    sid = session_id(request)
    if sid:
        sessions.pop(sid, None)
    STORE.clear()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    sess = require_session(request)
    return {
        "mode": sess["mode"],
        "email": sess["email"],
        "first_name": sess.get("first_name") or "",
        "last_name": sess.get("last_name") or "",
        "pending_2fa": sess.get("pending_2fa", False),
        "findmy": findmy_available(),
    }


@app.get("/api/accessories")
def list_accessories(request: Request) -> dict[str, Any]:
    sess = require_session(request)
    return {"accessories": sess["accessories"]}


@app.post("/api/accessories")
async def upload_accessory(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(None),
) -> dict[str, Any]:
    sess = require_session(request)
    if sess["mode"] == "demo":
        raise HTTPException(400, "Demo mode uses sample tags. Sign in with Apple ID to import your own JSON.")
    raw = (await file.read()).decode("utf-8")
    try:
        accessory = accessory_from_json_text(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            400,
            "Could not parse that file. Export accessory JSON with FindMy.py "
            f"(`python -m findmy decrypt`) on a Mac. Detail: {exc}",
        ) from exc
    item_id = str(uuid4())
    display = name or accessory_name(accessory, Path(file.filename or "accessory").stem)
    sess["accessories"].append(
        {
            "id": item_id,
            "name": display,
            "kind": "AirTag / Find My accessory",
            "identifier": getattr(accessory, "identifier", None),
            "battery": "Unknown",
            "location": None,
            "_json": persist_accessory(accessory) if hasattr(accessory, "to_json") else raw,
        }
    )
    public = {k: v for k, v in sess["accessories"][-1].items() if not k.startswith("_")}
    save_session(sess)
    return {"accessory": public}


@app.delete("/api/accessories/{item_id}")
def delete_accessory(item_id: str, request: Request) -> dict[str, Any]:
    sess = require_session(request)
    before = len(sess["accessories"])
    sess["accessories"] = [a for a in sess["accessories"] if a["id"] != item_id]
    if len(sess["accessories"]) == before:
        raise HTTPException(404, "Tag not found.")
    return {"ok": True}


@app.post("/api/accessories/refresh")
def refresh(request: Request) -> dict[str, Any]:
    sess = require_session(request)
    if sess["mode"] == "demo":
        return {"accessories": sess["accessories"], "note": "Demo locations are static samples."}
    if sess.get("pending_2fa"):
        raise HTTPException(400, "Finish two-factor authentication first.")
    if sess["account"] is None:
        raise HTTPException(400, "No Apple session.")
    if not sess["accessories"]:
        return {"accessories": []}

    loaded = []
    for item in sess["accessories"]:
        loaded.append(accessory_from_json_text(item["_json"]))

    try:
        reports = fetch_locations(sess["account"], loaded)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(502, f"Find My network request failed: {exc}") from exc

    public = []
    for idx, item in enumerate(sess["accessories"]):
        loc = reports.get(idx)
        if loc:
            item["location"] = loc
            item["battery"] = loc.get("battery") or item.get("battery") or "Unknown"
            try:
                item["_json"] = persist_accessory(loaded[idx])
            except Exception:
                pass
        public.append({k: v for k, v in item.items() if not k.startswith("_")})
    save_session(sess)
    return {"accessories": public}


if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
