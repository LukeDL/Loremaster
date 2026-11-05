"""Password hashing, token generation and canonical identifiers."""

from __future__ import annotations

import hashlib
import secrets
import unicodedata

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()
_DUMMY_HASH = _password_hash.hash("not-a-real-loremaster-password")


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username.strip()).casefold()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password_hash or _DUMMY_HASH
    valid = _password_hash.verify(password, candidate)
    return bool(password_hash) and valid


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    return secrets.compare_digest(token_hash(token), expected_hash)
