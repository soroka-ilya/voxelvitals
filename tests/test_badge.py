"""Unit tests for dynamic SVG status badge generation."""

import pytest
from app.domain.models import BadgeConfig, ServerStatus
from app.services.badge_service import generate_status_badge


def test_badge_online_generation():
    """Verify SVG badge format for an online server."""
    status = ServerStatus(
        address="mc.hypixel.net",
        is_online=True,
        players_online=25400,
        players_max=100000,
        latency_ms=32.0,
    )
    svg = generate_status_badge(status)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "mc.hypixel.net" in svg
    assert "25,400 online · 32ms" in svg
    assert "#10b981" in svg  # Emerald green


def test_badge_offline_generation():
    """Verify SVG badge format for an offline server."""
    status = ServerStatus(
        address="offline.domain.xyz",
        is_online=False,
    )
    svg = generate_status_badge(status)
    assert "offline.domain.xyz" in svg
    assert "offline" in svg
    assert "#ef4444" in svg  # Red indicator


def test_badge_custom_config():
    """Verify custom label and ping toggle in badge config."""
    status = ServerStatus(
        address="play.server.com:25565",
        is_online=True,
        players_online=150,
        players_max=500,
        latency_ms=45.0,
    )
    cfg = BadgeConfig(label="custom-node", show_ping=False)
    svg = generate_status_badge(status, cfg)
    assert "custom-node" in svg
    assert "150 / 500" in svg
    assert "45ms" not in svg


def test_badge_xml_escaping():
    """Verify XML special characters in server label are properly escaped."""
    status = ServerStatus(
        address="test&<fun>.com",
        is_online=False,
    )
    svg = generate_status_badge(status)
    assert "<fun>" not in svg
    assert "&lt;fun&gt;" in svg or "&amp;" in svg
