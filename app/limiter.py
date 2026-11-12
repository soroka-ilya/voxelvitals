"""Slowapi rate limiter configuration for VoxelVitals."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings


def get_real_client_ip(request: Request) -> str:
    """Extract client IP securely, honoring reverse proxy headers only from trusted proxies."""
    direct_ip = request.client.host if request.client and request.client.host else "127.0.0.1"

    # Only honor proxy headers if request originated from a trusted reverse proxy
    if direct_ip in settings.trusted_proxies:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Rightmost entry before proxy is closest client, or leftmost if single-hop nginx
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[0]

    return direct_ip


limiter = Limiter(key_func=get_real_client_ip)
