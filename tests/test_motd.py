"""Unit tests for Minecraft MOTD formatting and XSS sanitization."""

import pytest
from app.services.motd_formatter import format_motd_html, strip_minecraft_formatting


def test_strip_minecraft_formatting():
    """Verify all Minecraft formatting and color codes are stripped cleanly."""
    raw = "§aSurvival §7| §cPvP §lHardcore §#FFAABBNew!"
    plain = strip_minecraft_formatting(raw)
    assert plain == "Survival | PvP Hardcore New!"

    bungee_hex = "§x§f§f§a§a§0§0Warm Gold"
    assert strip_minecraft_formatting(bungee_hex) == "Warm Gold"

    # Test empty and None
    assert strip_minecraft_formatting("") == ""
    assert strip_minecraft_formatting(None) == ""


def test_format_motd_colors():
    """Verify § color codes generate correct colored spans."""
    raw = "§aOnline §cOffline"
    html_out = format_motd_html(raw)
    assert 'style="color: #55FF55;"' in html_out
    assert "Online" in html_out
    assert 'style="color: #FF5555;"' in html_out
    assert "Offline" in html_out
    # Check that tags are properly closed
    assert html_out.count("<span") == html_out.count("</span>")


def test_format_motd_styles():
    """Verify bold, italic, and reset tags."""
    raw = "§lBold §oItalic §rReset"
    html_out = format_motd_html(raw)
    assert "font-weight: bold;" in html_out
    assert "font-style: italic;" in html_out
    assert "Bold" in html_out
    assert "Italic" in html_out
    assert "Reset" in html_out


def test_format_motd_hex_colors():
    """Verify modern hex color codes in various formats."""
    # Standard modern hex
    raw = "&#10B981Emerald City"
    html_out = format_motd_html(raw)
    assert 'style="color: #10B981;"' in html_out
    assert "Emerald City" in html_out

    # Bungee hex notation
    bungee = "§x§1§0§b§9§8§1Bungee Emerald"
    bungee_html = format_motd_html(bungee)
    assert 'style="color: #10b981;"' in bungee_html
    assert "Bungee Emerald" in bungee_html


def test_motd_xss_protection():
    """Verify XSS attacks in MOTD are neutralized by escaping."""
    malicious = "<script>alert('xss')</script>§aSafe Text"
    html_out = format_motd_html(malicious)
    assert "<script>" not in html_out
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;" in html_out
    assert "Safe Text" in html_out


def test_motd_newlines():
    """Verify newlines translate to <br/> tags."""
    multiline = "Line 1\nLine 2\nLine 3"
    html_out = format_motd_html(multiline)
    assert "<br/>" in html_out
    assert html_out.count("<br/>") == 2


def test_motd_json_component():
    """Verify nested JSON text structures are properly flattened."""
    json_motd = {
        "text": "Welcome to ",
        "extra": [
            {"text": "VoxelVitals ", "color": "green"},
            {"text": "Server!"}
        ]
    }
    plain = strip_minecraft_formatting(json_motd)
    assert plain == "Welcome to VoxelVitals Server!"
