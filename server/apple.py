"""Thin wrapper around FindMy.py (https://github.com/malmeloo/FindMy.py)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

BATTERY_LEVEL = {0b00: "Full", 0b01: "Medium", 0b10: "Low", 0b11: "Very Low"}


def findmy_available() -> bool:
    try:
        import findmy  # noqa: F401

        return True
    except ImportError:
        return False


def battery_from_status(status: int | None) -> str:
    if status is None:
        return "Unknown"
    battery_id = (status >> 6) & 0b11
    return BATTERY_LEVEL.get(battery_id, "Unknown")


def create_account(libs_path: Path):
    from findmy import AppleAccount, LocalAnisetteProvider

    ani = LocalAnisetteProvider(libs_path=str(libs_path))
    return AppleAccount(ani)


def login(account, email: str, password: str):
    from findmy import LoginState

    state = account.login(email, password)
    return state, state == LoginState.REQUIRE_2FA, state == LoginState.LOGGED_IN


def load_2fa_methods(account) -> list[Any]:
    return list(account.get_2fa_methods())


def describe_2fa_methods(methods: list[Any]) -> list[dict[str, Any]]:
    from findmy import SmsSecondFactorMethod, TrustedDeviceSecondFactorMethod

    out: list[dict[str, Any]] = []
    for i, method in enumerate(methods):
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
    return out


def request_2fa(methods: list[Any], index: int) -> None:
    methods[index].request()


def submit_2fa(methods: list[Any], index: int, code: str) -> None:
    methods[index].submit(code)


def accessory_from_json_text(text: str):
    from findmy import FindMyAccessory

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        handle.write(text)
        path = handle.name
    try:
        return FindMyAccessory.from_json(path)
    finally:
        Path(path).unlink(missing_ok=True)


def accessory_name(accessory, fallback: str) -> str:
    name = getattr(accessory, "name", None)
    identifier = getattr(accessory, "identifier", None)
    if name:
        return str(name)
    if identifier:
        return str(identifier)
    return fallback


def fetch_locations(account, accessories: list[Any]) -> dict[int, dict[str, Any] | None]:
    reports = account.fetch_location(accessories)
    result: dict[int, dict[str, Any] | None] = {}
    for idx, accessory in enumerate(accessories):
        report = None
        if isinstance(reports, dict):
            report = reports.get(accessory)
        elif reports is not None and len(accessories) == 1:
            report = reports
        if report is None:
            result[idx] = None
            continue
        lat = getattr(report, "latitude", None)
        lon = getattr(report, "longitude", None)
        ts = getattr(report, "timestamp", None)
        status = getattr(report, "status", None)
        result[idx] = {
            "latitude": lat,
            "longitude": lon,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None,
            "status": status,
            "accuracy_m": getattr(report, "accuracy", None) or getattr(report, "horizontal_accuracy", None),
            "battery": battery_from_status(status),
        }
    return result


def persist_accessory(accessory) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        path = handle.name
    accessory.to_json(path)
    data = Path(path).read_text()
    Path(path).unlink(missing_ok=True)
    json.loads(data)
    return data
