"""Authenticated encryption helpers for persisted inflection snapshots."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

FORMAT_HEADER = "TRADER_SNAPSHOT_V1"


def _fernet(secret: str) -> Fernet:
    if not secret:
        raise RuntimeError("SNAPSHOT_ENCRYPTION_KEY is required")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def key_id(secret: str) -> str:
    """Return a non-secret identifier for diagnosing key-rotation issues."""
    if not secret:
        raise RuntimeError("SNAPSHOT_ENCRYPTION_KEY is required")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def encrypt_json(payload: dict[str, Any], secret: str) -> str:
    """Serialize and encrypt a JSON object into an ASCII-safe text envelope."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = _fernet(secret).encrypt(raw).decode("ascii")
    return f"{FORMAT_HEADER}\n{token}\n"


def decrypt_json(text: str, secret: str) -> dict[str, Any]:
    """Decrypt a snapshot envelope and return its JSON object."""
    lines = text.strip().splitlines()
    if len(lines) != 2 or lines[0] != FORMAT_HEADER:
        raise ValueError("unsupported encrypted snapshot format")
    try:
        raw = _fernet(secret).decrypt(lines[1].encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("snapshot decryption failed; wrong key or corrupted data") from exc
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("decrypted snapshot must contain a JSON object")
    return payload
