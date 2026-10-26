"""Shields.io-style SVG badge generator for Minecraft servers."""

import html
from typing import Optional
from app.domain.models import BadgeConfig, ServerStatus


def _estimate_text_width(text: str) -> int:
    """Approximate width in pixels for 11px font."""
    return max(int(len(text) * 6.8) + 12, 30)


def generate_status_badge(
    status: ServerStatus, config: Optional[BadgeConfig] = None
) -> str:
    """Generate dynamic SVG status badge styled like Shields.io."""
    cfg = config or BadgeConfig()
    label = cfg.label if cfg.label != "minecraft" else status.address.split(":")[0]
    
    if status.is_online:
        if cfg.show_ping and status.latency_ms > 0:
            value = f"{status.players_online:,} online · {int(status.latency_ms)}ms"
        else:
            value = f"{status.players_online:,} / {status.players_max:,}"
        right_bg = "#10b981"  # Emerald
    else:
        value = "offline"
        right_bg = "#ef4444"  # Red

    left_bg = "#1e293b"  # Deep slate

    left_w = _estimate_text_width(label)
    right_w = _estimate_text_width(value)
    total_w = left_w + right_w
    h = 20

    left_x = left_w / 2
    right_x = left_w + (right_w / 2)

    escaped_label = html.escape(label)
    escaped_value = html.escape(value)
    title = f"{escaped_label}: {escaped_value}"


    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{h}" role="img" aria-label="{title}">
  <title>{title}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_w}" height="{h}" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_w}" height="{h}" fill="{left_bg}"/>
    <rect x="{left_w}" width="{right_w}" height="{h}" fill="{right_bg}"/>
    <rect width="{total_w}" height="{h}" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{left_x * 10:.0f}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(left_w - 12) * 10}">{escaped_label}</text>
    <text x="{left_x * 10:.0f}" y="140" transform="scale(.1)" fill="#fff" textLength="{(left_w - 12) * 10}">{escaped_label}</text>
    <text aria-hidden="true" x="{right_x * 10:.0f}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(right_w - 12) * 10}">{escaped_value}</text>
    <text x="{right_x * 10:.0f}" y="140" transform="scale(.1)" fill="#fff" textLength="{(right_w - 12) * 10}">{escaped_value}</text>
  </g>
</svg>"""
    return svg
