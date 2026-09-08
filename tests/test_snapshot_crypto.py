from __future__ import annotations

from unittest.mock import patch

import pytest

from src.data.snapshot_crypto import (
    FORMAT_HEADER,
    decrypt_json,
    encrypt_json,
    key_id,
    snapshot_encryption_secret,
)


def test_snapshot_crypto_round_trip_hides_plaintext() -> None:
    payload = {"ticker": "1111.T", "classification": "EARLY_CANDIDATE", "score": 80.0}
    encrypted = encrypt_json(payload, "secret-key")

    assert encrypted.startswith(f"{FORMAT_HEADER}\n")
    assert "1111.T" not in encrypted
    assert "EARLY_CANDIDATE" not in encrypted
    assert decrypt_json(encrypted, "secret-key") == payload


def test_snapshot_crypto_rejects_wrong_key() -> None:
    encrypted = encrypt_json({"value": 1}, "secret-key")
    with pytest.raises(ValueError, match="decryption failed"):
        decrypt_json(encrypted, "wrong-key")


def test_snapshot_key_id_is_stable_and_non_secret() -> None:
    assert key_id("secret-key") == key_id("secret-key")
    assert key_id("secret-key") != key_id("other-key")
    assert "secret-key" not in key_id("secret-key")


def test_snapshot_encryption_requires_a_dedicated_key() -> None:
    with (
        patch.dict("os.environ", {"JQUANTS_API_KEY": "api-key"}, clear=True),
        pytest.raises(RuntimeError, match="SNAPSHOT_ENCRYPTION_KEY is required"),
    ):
        snapshot_encryption_secret()

    with patch.dict("os.environ", {"SNAPSHOT_ENCRYPTION_KEY": "snapshot-key"}, clear=True):
        assert snapshot_encryption_secret() == "snapshot-key"
