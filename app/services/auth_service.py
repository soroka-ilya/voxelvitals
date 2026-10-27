"""Authentication helper service for passwords and sessions."""

import hashlib
import os
import secrets
from typing import Optional
from fastapi import Request
from app.repository import ServerRepository


def hash_password(password: str) -> str:
    """Hash password with a random 16-byte salt using SHA-256."""
    salt = secrets.token_hex(16)
    key = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${key}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify raw password against salt$hash string."""
    try:
        salt, key = password_hash.split("$", 1)
        expected_key = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(key, expected_key)
    except Exception:
        return False


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
