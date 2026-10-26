"""Minecraft MOTD formatting and sanitization utility.

Converts legacy color codes (§0-§f), formatting codes (§l, §o, §n, §m, §k, §r),
and hex color codes (&#RRGGBB, §#RRGGBB, §x§r§r§g§g§b§b) into safe HTML.
Protects against XSS injections by HTML-escaping all raw input.
"""

import html
import re
from typing import Any

COLOR_MAP = {
    "0": "#000000",
    "1": "#0000AA",
    "2": "#00AA00",
    "3": "#00AAAA",
    "4": "#AA0000",
    "5": "#AA00AA",
    "6": "#FFAA00",
    "7": "#AAAAAA",
    "8": "#555555",
    "9": "#5555FF",
    "a": "#55FF55",
    "b": "#55FFFF",
    "c": "#FF5555",
    "d": "#FF55FF",
    "e": "#FFFF55",
    "f": "#FFFFFF",
}

STYLE_MAP = {
    "l": "font-weight: bold;",
    "m": "text-decoration: line-through;",
    "n": "text-decoration: underline;",
    "o": "font-style: italic;",
}


def _normalize_raw_input(raw: Any) -> str:
    """Flatten raw MOTD (string, dict, or list) into a single string."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Could be Minecraft JSON text component: {"text": "...", "extra": [...]}
        out = raw.get("text", "")
        for extra in raw.get("extra", []):
            out += _normalize_raw_input(extra)
        return out
    if isinstance(raw, list):
        return "".join(_normalize_raw_input(item) for item in raw)
    return str(raw)


def strip_minecraft_formatting(raw: Any) -> str:
    """Remove all color codes, style codes and hex tags to yield plain text."""
    text = _normalize_raw_input(raw)
    # Replace BungeeCord/Spigot hex §x§r§r§g§g§b§b
    text = re.sub(r"§x(§[0-9a-fA-F]){6}", "", text)
    # Replace &#RRGGBB or §#RRGGBB
    text = re.sub(r"[&§]#[0-9a-fA-F]{6}", "", text)
    # Replace standard §X and &X formatting codes
    text = re.sub(r"[§&][0-9a-fk-orA-FK-OR]", "", text)
    return text.strip()


def format_motd_html(raw: Any) -> str:
    """Safely convert Minecraft formatted MOTD into sanitized HTML spans."""
    text = _normalize_raw_input(raw)
    if not text:
        return '<span class="text-slate-400">A Minecraft Server</span>'

    # Normalize Bungee hex §x§r§r§g§g§b§b to §#rrggbb
    def _bungee_hex_repl(m):
        chars = [c for c in m.group(0) if c not in ("§", "x")]
        return f"§#{''.join(chars)}"

    text = re.sub(r"§x(§[0-9a-fA-F]){6}", _bungee_hex_repl, text)
    # Normalize &#RRGGBB to §#rrggbb
    text = re.sub(r"&#([0-9a-fA-F]{6})", r"§#\1", text)

    # Split into lines so newlines become <br/>
    lines = text.split("\n")
    html_lines = []

    for line in lines:
        tokens = re.split(r"(§#[0-9a-fA-F]{6}|§[0-9a-fk-orA-FK-OR])", line)
        open_spans = 0
        line_html = []

        for token in tokens:
            if not token:
                continue
            if token.startswith("§#"):
                hex_color = token[2:]
                line_html.append(f'<span style="color: #{hex_color};">')
                open_spans += 1
            elif token.startswith("§"):
                code = token[1].lower()
                if code in COLOR_MAP:
                    # Color resets all styles in vanilla Minecraft
                    while open_spans > 0:
                        line_html.append("</span>")
                        open_spans -= 1
                    line_html.append(f'<span style="color: {COLOR_MAP[code]};">')
                    open_spans += 1
                elif code in STYLE_MAP:
                    line_html.append(f'<span style="{STYLE_MAP[code]}">')
                    open_spans += 1
                elif code == "k":
                    line_html.append('<span class="mc-obfuscated">')
                    open_spans += 1
                elif code == "r":
                    while open_spans > 0:
                        line_html.append("</span>")
                        open_spans -= 1
            else:
                line_html.append(html.escape(token))

        while open_spans > 0:
            line_html.append("</span>")
            open_spans -= 1

        html_lines.append("".join(line_html))

    return "<br/>".join(html_lines)
