"""Encrypted local persistence for the Find Me session.

The FindMy.py account JSON contains reusable authentication material and the
accessory records contain private keys. Keep both encrypted and local.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet


class EncryptedStore:
    def __init__(self, path: Path, key_path: Path) -> None:
        self.path = path
        self.key_path = key_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            key = self.key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            self.key_path.chmod(0o600)
        self._fernet = Fernet(key)

    def save(self, value: dict[str, Any]) -> None:
        encrypted = self._fernet.encrypt(json.dumps(value).encode("utf-8"))
        self.path.write_bytes(encrypted)
        self.path.chmod(0o600)

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            decrypted = self._fernet.decrypt(self.path.read_bytes())
            value = json.loads(decrypted.decode("utf-8"))
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

