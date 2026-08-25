"""Static sample tags for demo mode (no Apple credentials)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)

DEMO_ACCESSORIES = [
    {
        "id": "demo-keys",
        "name": "Keys",
        "kind": "AirTag",
        "identifier": "KEYS-DEMO",
        "battery": "Medium",
        "location": {
            "latitude": 42.6977,
            "longitude": 23.3219,
            "accuracy_m": 18,
            "timestamp": (NOW - timedelta(minutes=4)).isoformat(),
            "status": 64,
        },
    },
    {
        "id": "demo-backpack",
        "name": "Backpack",
        "kind": "AirTag",
        "identifier": "BAG-DEMO",
        "battery": "Full",
        "location": {
            "latitude": 42.6936,
            "longitude": 23.3347,
            "accuracy_m": 32,
            "timestamp": (NOW - timedelta(minutes=22)).isoformat(),
            "status": 0,
        },
    },
    {
        "id": "demo-case",
        "name": "AirPods Case",
        "kind": "Find My accessory",
        "identifier": "PODS-DEMO",
        "battery": "Low",
        "location": {
            "latitude": 42.6881,
            "longitude": 23.3186,
            "accuracy_m": 45,
            "timestamp": (NOW - timedelta(hours=3)).isoformat(),
            "status": 128,
        },
    },
    {
        "id": "demo-wallet",
        "name": "Wallet",
        "kind": "AirTag",
        "identifier": "WALLET-DEMO",
        "battery": "Very Low",
        "location": None,
    },
]
