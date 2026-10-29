"""Visitor tracking and telemetry analytics service."""

import hashlib
import re
import secrets
from typing import Tuple
from fastapi import Request


def hash_ip(ip: str) -> str:
    """Anonymize IP address with SHA-256 digest prefix."""
    return hashlib.sha256((ip + "_voxel_salt_2026").encode("utf-8")).hexdigest()[:16]


def parse_device_and_browser(user_agent: str) -> Tuple[str, str]:
    """Parse User-Agent into normalized (device_type, browser)."""
    ua = (user_agent or "").lower()

    # Device
    if any(k in ua for k in ("mobile", "android", "iphone", "ipod")):
        device = "mobile"
    elif "ipad" in ua or "tablet" in ua:
        device = "tablet"
    else:
        device = "desktop"

    # Browser
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua and "safari" in ua and "edg" not in ua and "opr" not in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "opr" in ua or "opera" in ua:
        browser = "Opera"
    else:
        browser = "Other"

    return device, browser


def get_or_create_visitor_id(request: Request) -> Tuple[str, bool]:
    """Extract or generate unique visitor tracking identifier."""
    vid = request.cookies.get("vv_vid")
    if vid and len(vid) >= 8:
        return vid, False
    new_vid = f"vv_{secrets.token_urlsafe(12)}"
    return new_vid, True
