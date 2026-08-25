#!/usr/bin/env python3
"""Validate Android FindMy Python packaging and bridge imports locally.

Run from the repo root (or android/):

  python android/check_python.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "third_party" / "FindMy.py"
BRIDGE = ROOT / "app" / "src" / "main" / "python"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    if not VENDOR.is_dir():
        fail(f"missing vendor tree: {VENDOR}")
    if not BRIDGE.is_dir():
        fail(f"missing bridge dir: {BRIDGE}")

    sys.path.insert(0, str(VENDOR))
    sys.path.insert(0, str(BRIDGE))

    required = [
        "findmy",
        "findmy.accessory",
        "findmy.reports",
        "findmy.reports.account",
        "findmy.reports.anisette",
        "findmy.util",
        "bridge",
    ]
    for name in required:
        try:
            importlib.import_module(name)
            print(f"ok  import {name}")
        except Exception as exc:  # noqa: BLE001
            fail(f"import {name}: {exc}")

    # Compile-check bridge.py for IndentationError / SyntaxError
    bridge_path = BRIDGE / "bridge.py"
    source = bridge_path.read_text(encoding="utf-8")
    try:
        compile(source, str(bridge_path), "exec")
        print(f"ok  compile {bridge_path.name}")
    except SyntaxError as exc:
        fail(f"compile {bridge_path.name}: {exc}")

    # Confirm setuptools would package submodules
    try:
        from setuptools import find_packages
    except ImportError:
        print("warn setuptools not installed; skip package discovery check")
    else:
        packages = find_packages(where=str(VENDOR), include=["findmy*"])
        expected = {"findmy", "findmy.reports", "findmy.util", "findmy.scanner"}
        missing = expected - set(packages)
        if missing:
            fail(f"setuptools packages missing {sorted(missing)}; found {packages}")
        print(f"ok  packages {sorted(packages)}")

    # Smoke the symbols the app actually imports
    from findmy.accessory import FindMyAccessory  # noqa: F401
    from findmy.reports import (  # noqa: F401
        AppleAccount,
        LoginState,
        RemoteAnisetteProvider,
        SmsSecondFactorMethod,
        TrustedDeviceSecondFactorMethod,
    )

    print("ok  required symbols")
    print("PASS")


if __name__ == "__main__":
    main()
