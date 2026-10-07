from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Optional


def hash_password(password: str, salt_hex: str, iterations: int = 250_000) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()


def verify_basic(header: Optional[str], username: str, salt_hex: str, expected_hash: str, iterations: int = 250_000) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
        got_user, got_password = raw.split(":", 1)
    except Exception:
        return False
    if not hmac.compare_digest(got_user, username):
        return False
    got_hash = hash_password(got_password, salt_hex, iterations)
    return hmac.compare_digest(got_hash, expected_hash)
