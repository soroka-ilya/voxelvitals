"""Authentication helper service for passwords and sessions."""

import hashlib
import os
import secrets
from typing import Optional
from fastapi import Request
from app.repository import ServerRepository


def hash_password(password: str) -> str:
    """Hash password using memory-hard scrypt KDF with random salt."""
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p).hex()
    return f"scrypt${n}${r}${p}${salt.hex()}${derived}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify raw password against scrypt or legacy salt$sha256 hash string."""
    try:
        if password_hash.startswith("scrypt$"):
            parts = password_hash.split("$")
            if len(parts) == 6:
                _, n_str, r_str, p_str, salt_hex, key = parts
                n, r, p = int(n_str), int(r_str), int(p_str)
                salt = bytes.fromhex(salt_hex)
                derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p).hex()
                return secrets.compare_digest(key, derived)
        # Legacy SHA-256 fallback (salt$hash)
        salt, key = password_hash.split("$", 1)
        expected_key = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(key, expected_key)
    except Exception:
        return False


def is_legacy_hash(password_hash: str) -> bool:
    """Check if hash requires upgrade to scrypt."""
    return not password_hash.startswith("scrypt$")


def generate_session_token() -> str:
    """Generate a high-entropy random URL-safe token."""
    return secrets.token_urlsafe(32)


async def get_current_user_from_request(
    request: Request, repo: ServerRepository
) -> Optional[dict]:
    """Retrieve current authenticated user from session cookie or Authorization header."""
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        return None

    return await repo.get_user_by_session(token)
