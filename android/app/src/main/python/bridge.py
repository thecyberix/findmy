"""FindMy.py bridge for the Android app. Uses remote Anisette (no native ani_libs)."""

from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

ANI_URL = "https://ani.sidestore.io"
BATTERY_LEVEL = {0b00: "Full", 0b01: "Medium", 0b10: "Low", 0b11: "Very Low"}

_account = None
_methods: list[Any] = []
_accessories: list[dict[str, Any]] = []


def _ok(**kwargs: Any) -> str:
    payload = {"ok": True, **kwargs}
    return json.dumps(payload)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def _battery(status: int | None) -> str:
    if status is None:
        return "Unknown"
    return BATTERY_LEVEL.get((status >> 6) & 0b11, "Unknown")


def _accessory_from_text(text: str):
    from findmy.accessory import FindMyAccessory

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        handle.write(text)
        path = handle.name
    try:
        return FindMyAccessory.from_json(path)
    finally:
        Path(path).unlink(missing_ok=True)


def _persist_accessory(accessory) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        path = handle.name
    accessory.to_json(path)
    data = Path(path).read_text(encoding="utf-8")
    Path(path).unlink(missing_ok=True)
    return data


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def _dump_accessories() -> list[dict[str, Any]]:
    return list(_accessories)


def _account_json() -> Any:
    data = _account.to_json()
    if isinstance(data, str):
        return json.loads(data)
    return data


def restore(account_json: str, accessories_json: str) -> str:
    global _account, _methods, _accessories
    from findmy.reports import AppleAccount

    try:
        payload = json.loads(account_json)
        ani = payload.get("anisette") if isinstance(payload, dict) else None
        if isinstance(ani, dict) and ani.get("type") == "aniRemote" and not ani.get("adi_pb"):
            return _err(
                "Apple session needs an upgrade. Sign out and sign in again "
                "(one time) so a private Anisette device can be created."
            )
        _account = AppleAccount.from_json(payload if isinstance(payload, dict) else account_json)
        _methods = []
        _accessories = json.loads(accessories_json) if accessories_json else []
        return _ok(accessories=_dump_accessories())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


def login(email: str, password: str) -> str:
    global _account, _methods, _accessories
    from findmy.reports import AppleAccount, LoginState, RemoteAnisetteProvider

    try:
        ani = RemoteAnisetteProvider(ANI_URL)
        _account = AppleAccount(ani)
        state = _account.login(email.strip(), password)
        needs_2fa = state == LoginState.REQUIRE_2FA
        logged_in = state == LoginState.LOGGED_IN
        _accessories = []
        _methods = list(_account.get_2fa_methods()) if needs_2fa else []
        return _ok(
            needs_2fa=needs_2fa,
            logged_in=logged_in,
            methods=_describe_methods(),
            account=_account_json() if logged_in else None,
            accessories=[],
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _err(f"Apple sign-in failed: {exc}")


def _describe_methods() -> list[dict[str, Any]]:
    from findmy.reports import SmsSecondFactorMethod, TrustedDeviceSecondFactorMethod

    out: list[dict[str, Any]] = []
    for i, method in enumerate(_methods):
        if isinstance(method, TrustedDeviceSecondFactorMethod):
            out.append({"index": i, "type": "trusted_device", "label": "Trusted device"})
        elif isinstance(method, SmsSecondFactorMethod):
            out.append(
                {
                    "index": i,
                    "type": "sms",
                    "label": f"SMS ({method.phone_number})",
                    "phone": method.phone_number,
                }
            )
        else:
            out.append({"index": i, "type": "other", "label": type(method).__name__})
    # Prefer trusted device: SMS against public Anisette servers often returns 401.
    out.sort(key=lambda item: 0 if item["type"] == "trusted_device" else 1)
    return out


def request_2fa(index: int) -> str:
    try:
        _methods[index].request()
        return _ok()
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "401" in message:
            message = (
                f"{message}. Apple rejected this challenge (common with shared Anisette). "
                "Cancel, sign in again, and prefer Trusted device if listed; tap Send soon after login."
            )
        return _err(message)


def submit_2fa(index: int, code: str) -> str:
    try:
        _methods[index].submit(code.strip())
        return _ok(account=_account_json(), accessories=_accessories)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


def add_accessory(json_text: str, fallback_name: str) -> str:
    try:
        accessory = _accessory_from_text(json_text)
    except Exception as exc:  # noqa: BLE001
        return _err(f"Invalid JSON: {exc}")
    name = getattr(accessory, "name", None) or getattr(accessory, "identifier", None) or fallback_name
    item = {
        "id": str(uuid4()),
        "name": str(name),
        "battery": "Unknown",
        "location": None,
        "_json": _persist_accessory(accessory) if hasattr(accessory, "to_json") else json_text,
    }
    _accessories.append(item)
    return _ok(accessory=_public(item), accessories=_dump_accessories())


def remove_accessory(item_id: str) -> str:
    global _accessories
    before = len(_accessories)
    _accessories = [item for item in _accessories if item["id"] != item_id]
    if len(_accessories) == before:
        return _err("Not found.")
    return _ok(accessories=_dump_accessories())


def _has_anisette_v3() -> bool:
    async_acc = getattr(_account, "_asyncacc", _account)
    ani = getattr(async_acc, "_anisette", None)
    return bool(getattr(ani, "_adi_pb", None) and getattr(ani, "_identifier", None))


def refresh() -> str:
    if _account is None:
        return _err("Not signed in.")
    if not _has_anisette_v3():
        return _err(
            "Apple session needs a one-time upgrade. Sign out and sign in again "
            "so the app can create a private Anisette device."
        )
    if not _accessories:
        return _ok(accessories=[])
    loaded = []
    for item in _accessories:
        loaded.append(_accessory_from_text(item["_json"]))
    try:
        reports = _account.fetch_location(loaded)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        message = str(exc)
        if "Email verification failed" in message or "401" in message or "Not authorized" in message:
            message = (
                f"{message} Sign out and sign in again once so the app can "
                "create a private Anisette device (needed after updates)."
            )
        return _err(f"Find My request failed: {message}")

    for idx, item in enumerate(_accessories):
        report = None
        if isinstance(reports, dict):
            report = reports.get(loaded[idx])
        elif reports is not None and len(loaded) == 1:
            report = reports
        if report is None:
            continue
        lat = getattr(report, "latitude", None)
        lon = getattr(report, "longitude", None)
        ts = getattr(report, "timestamp", None)
        status = getattr(report, "status", None)
        loc = {
            "latitude": lat,
            "longitude": lon,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None,
            "battery": _battery(status),
        }
        item["location"] = loc
        item["battery"] = loc["battery"]
        try:
            item["_json"] = _persist_accessory(loaded[idx])
        except Exception:
            pass
    return _ok(accessories=_dump_accessories(), account=_account_json())


def logout() -> str:
    global _account, _methods, _accessories
    _account = None
    _methods = []
    _accessories = []
    return _ok()
