"""Minecraft server alias registry, address resolution, and curated catalog."""

import base64
import re
from typing import Any, Dict, List, Optional


def _make_svg_icon(text: str, bg_color: str, fg_color: str = "#ffffff") -> str:
    """Generate inline SVG data URI for server icon with distinct brand styling."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">'
        f'<rect width="48" height="48" rx="10" fill="{bg_color}"/>'
        f'<text x="24" y="29" font-family="JetBrains Mono, monospace" font-size="15" '
        f'font-weight="700" fill="{fg_color}" text-anchor="middle" dominant-baseline="middle">{text}</text>'
        f'</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# Curated catalog servers with rich metadata
CURATED_SERVERS: List[Dict[str, Any]] = [
    {
        "id": "hypixel",
        "name": "Hypixel Network",
        "address": "mc.hypixel.net",
        "category": "minigames",
        "category_label": "Мини-игры",
        "description": "Крупнейший сервер в мире: BedWars, SkyWars, SkyBlock и турниры",
        "icon": _make_svg_icon("HY", "#b45309", "#fef3c7"),
        "edition": "java",
        "tags": ["minigames", "bedwars", "skyblock", "hypixel", "hyp"],
    },
    {
        "id": "2b2t",
        "name": "2b2t Anarchy",
        "address": "2b2t.org",
        "category": "anarchy",
        "category_label": "Анархия и Выживание",
        "description": "Старейший сервер анархии без правил, чисток карты и цензуры с 2010 года",
        "icon": _make_svg_icon("2B", "#1e1e24", "#e2e8f0"),
        "edition": "java",
        "tags": ["anarchy", "survival", "2b2t", "2b", "vanilla"],
    },
    {
        "id": "donutsmp",
        "name": "DonutSMP",
        "address": "donutsmp.net",
        "category": "anarchy",
        "category_label": "Анархия и Выживание",
        "description": "Хардкорный ванильный SMP с экономикой, кланами и рейдами баз",
        "icon": _make_svg_icon("DS", "#be185d", "#fdf2f8"),
        "edition": "java",
        "tags": ["anarchy", "survival", "smp", "hardcore", "donutsmp", "donut"],
    },
    {
        "id": "cubecraft",
        "name": "CubeCraft Games",
        "address": "play.cubecraft.net",
        "category": "minigames",
        "category_label": "Мини-игры",
        "description": "Популярная сеть мини-игр: EggWars, Lucky Islands и Tower Defence",
        "icon": _make_svg_icon("CC", "#0369a1", "#e0f2fe"),
        "edition": "java",
        "tags": ["minigames", "eggwars", "cubecraft", "cube craft"],
    },
    {
        "id": "gommehd",
        "name": "GommeHD.net",
        "address": "gommehd.net",
        "category": "minigames",
        "category_label": "Мини-игры",
        "description": "Ведущий европейский сервер мини-игр с BedWars, TTT и JumpLeague",
        "icon": _make_svg_icon("GHD", "#c2410c", "#ffedd5"),
        "edition": "java",
        "tags": ["minigames", "bedwars", "gomme", "gommehd"],
    },
    {
        "id": "vimeworld",
        "name": "VimeWorld",
        "address": "mc.vimeworld.net",
        "category": "minigames",
        "category_label": "Мини-игры",
        "description": "Крупнейший русскоязычный проект мини-игр и аркад",
        "icon": _make_svg_icon("VW", "#1d4ed8", "#dbeafe"),
        "edition": "java",
        "tags": ["minigames", "vimeworld", "vime", "vime world"],
    },
    {
        "id": "wynncraft",
        "name": "Wynncraft MMORPG",
        "address": "play.wynncraft.com",
        "category": "rpg",
        "category_label": "MMORPG",
        "description": "Масштабная фэнтези RPG в Minecraft: квесты, подземелья, боссы и классы",
        "icon": _make_svg_icon("WY", "#4338ca", "#e0e7ff"),
        "edition": "java",
        "tags": ["rpg", "mmorpg", "quests", "wynncraft", "wynn", "wynn craft"],
    },
    {
        "id": "manacube",
        "name": "ManaCube",
        "address": "play.manacube.com",
        "category": "rpg",
        "category_label": "MMORPG",
        "description": "Популярный мир паркура, Skyblock, Survival и кастомных RPG-механик",
        "icon": _make_svg_icon("MC", "#047857", "#d1fae5"),
        "edition": "java",
        "tags": ["rpg", "parkour", "skyblock", "manacube", "mana cube", "mana"],
    },
    {
        "id": "complex",
        "name": "Complex Gaming",
        "address": "hub.mc-complex.com",
        "category": "rpg",
        "category_label": "MMORPG",
        "description": "Мульти-модовый сервер Pixelmon, Cobblemon, FTB и Vanilla SMP",
        "icon": _make_svg_icon("CX", "#7c3aed", "#ede9fe"),
        "edition": "java",
        "tags": ["rpg", "pixelmon", "cobblemon", "complex", "complex gaming"],
    },
    {
        "id": "minemen",
        "name": "Minemen Club",
        "address": "minemen.club",
        "category": "pvp",
        "category_label": "PvP",
        "description": "Профессиональная соревновательная арена дуэлей и Ranked PvP",
        "icon": _make_svg_icon("MMC", "#b91c1c", "#fee2e2"),
        "edition": "java",
        "tags": ["pvp", "duels", "ranked", "practice", "minemen", "mmc"],
    },
]


# Direct alias lookup table mapping common abbreviations to primary domain/IP
ALIAS_MAP: Dict[str, str] = {
    # 2b2t
    "2b2t": "2b2t.org",
    "2b 2t": "2b2t.org",
    "2b": "2b2t.org",
    "2b2t anarchy": "2b2t.org",
    "2b2t.org": "2b2t.org",
    # Hypixel
    "hypixel": "mc.hypixel.net",
    "hypixel network": "mc.hypixel.net",
    "hyp": "mc.hypixel.net",
    "hypixel.net": "mc.hypixel.net",
    "mc.hypixel.net": "mc.hypixel.net",
    # CubeCraft
    "cubecraft": "play.cubecraft.net",
    "cube craft": "play.cubecraft.net",
    "cubecraft games": "play.cubecraft.net",
    "cubecraft network": "play.cubecraft.net",
    "play.cubecraft.net": "play.cubecraft.net",
    # DonutSMP
    "donutsmp": "donutsmp.net",
    "donut smp": "donutsmp.net",
    "donut": "donutsmp.net",
    "donutsmp.net": "donutsmp.net",
    # Wynncraft
    "wynncraft": "play.wynncraft.com",
    "wynn craft": "play.wynncraft.com",
    "wynn": "play.wynncraft.com",
    "play.wynncraft.com": "play.wynncraft.com",
    # Minemen Club
    "minemen": "minemen.club",
    "minemen club": "minemen.club",
    "mmc": "minemen.club",
    "minemen.club": "minemen.club",
    # GommeHD
    "gommehd": "gommehd.net",
    "gomme hd": "gommehd.net",
    "gomme": "gommehd.net",
    "gommehd.net": "gommehd.net",
    # ManaCube
    "manacube": "play.manacube.com",
    "mana cube": "play.manacube.com",
    "mana": "play.manacube.com",
    "play.manacube.com": "play.manacube.com",
    # VimeWorld
    "vimeworld": "mc.vimeworld.net",
    "vime world": "mc.vimeworld.net",
    "vime": "mc.vimeworld.net",
    "mc.vimeworld.net": "mc.vimeworld.net",
    # Complex Gaming
    "complex": "hub.mc-complex.com",
    "complex gaming": "hub.mc-complex.com",
    "complex mc": "hub.mc-complex.com",
    "pixelmon complex": "hub.mc-complex.com",
    "hub.mc-complex.com": "hub.mc-complex.com",
}


def normalize_query(query: str) -> str:
    """Clean and normalize server search query."""
    q = query.strip()
    if not q:
        return ""
    # Strip protocols like minecraft:// or https://
    q = re.sub(r"^[a-zA-Z]+://", "", q)
    # Strip trailing slashes
    q = q.rstrip("/")
    return q


def _split_host_port(address: str) -> tuple[str, Optional[int]]:
    """Separate hostname from optional port."""
    addr = address.strip()
    if not addr:
        return "", None

    # Bracketed IPv6 notation: [2001:db8::1]:25565 or [2001:db8::1]
    if addr.startswith("["):
        if "]:" in addr:
            parts = addr.rsplit("]:", 1)
            host = parts[0] + "]"
            port_str = parts[1]
            if port_str.isdigit():
                return host, int(port_str)
            return addr, None
        return addr, None

    # Unbracketed IPv6 with multiple colons has no port
    if addr.count(":") > 1:
        return addr, None

    if ":" in addr:
        parts = addr.rsplit(":", 1)
        if parts[1].isdigit():
            return parts[0].strip(), int(parts[1])
    return addr, None


def resolve_address(query: str, default_tld: str = ".net") -> str:
    """Resolve shorthand alias or query into canonical server address.

    Performs TLD fallback if no domain extension is present.
    """
    clean = normalize_query(query)
    if not clean:
        return ""

    host, port = _split_host_port(clean)
    host_lower = host.lower()

    # Direct match in alias map
    if host_lower in ALIAS_MAP:
        resolved_host = ALIAS_MAP[host_lower]
        return f"{resolved_host}:{port}" if port else resolved_host

    # Stripped symbols/spaces match (e.g. "2b 2t" -> "2b2t")
    alphanumeric_key = re.sub(r"[^a-z0-9]", "", host_lower)
    if alphanumeric_key in ALIAS_MAP:
        resolved_host = ALIAS_MAP[alphanumeric_key]
        return f"{resolved_host}:{port}" if port else resolved_host

    # Remove noise words (network, server, etc.)
    stripped_noise = re.sub(
        r"\b(network|server|gaming|club|anarchy|smp|games|net|org|com)\b",
        "",
        host_lower,
    ).strip()
    stripped_noise_clean = re.sub(r"[^a-z0-9]", "", stripped_noise)
    if stripped_noise in ALIAS_MAP:
        resolved_host = ALIAS_MAP[stripped_noise]
        return f"{resolved_host}:{port}" if port else resolved_host
    if stripped_noise_clean in ALIAS_MAP:
        resolved_host = ALIAS_MAP[stripped_noise_clean]
        return f"{resolved_host}:{port}" if port else resolved_host

    # Check if host is localhost or already contains a domain dot or is an IPv6 address
    if host_lower == "localhost" or "." in host or host.count(":") > 1 or host.startswith("["):
        sanitized_host = re.sub(r"\s+", "", host)
        return f"{sanitized_host}:{port}" if port else sanitized_host

    # Fallback to appending default TLD if no dot is present (remove spaces for valid hostname)
    sanitized_host = re.sub(r"\s+", "", host)
    tld = default_tld if default_tld.startswith(".") else f".{default_tld}"
    fallback_host = f"{sanitized_host}{tld}"
    return f"{fallback_host}:{port}" if port else fallback_host


def get_curated_catalog(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return list of curated Minecraft servers, optionally filtered by genre category."""
    if not category or category == "all":
        return list(CURATED_SERVERS)
    return [s for s in CURATED_SERVERS if s.get("category") == category]


def search_suggestions(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Provide autocomplete suggestions matching the query."""
    clean_q = normalize_query(query).lower()
    if not clean_q:
        return [
            {
                "name": s["name"],
                "address": s["address"],
                "category": s["category"],
                "category_label": s.get("category_label", s["category"]),
                "icon": s["icon"],
                "description": s.get("description", ""),
            }
            for s in CURATED_SERVERS[:limit]
        ]

    q_host, _ = _split_host_port(clean_q)
    resolved = resolve_address(clean_q)
    resolved_host, _ = _split_host_port(resolved) if resolved else ("", None)
    resolved_host_lower = resolved_host.lower() if resolved_host else ""
    compact_q = re.sub(r"[^a-z0-9]", "", clean_q)

    scored_results: List[tuple[int, Dict[str, Any]]] = []

    for s in CURATED_SERVERS:
        score = 0
        name_lower = s["name"].lower()
        addr_lower = s["address"].lower()
        cat_lower = s["category"].lower()
        tags = [t.lower() for t in s.get("tags", [])]

        compact_id = re.sub(r"[^a-z0-9]", "", s["id"].lower())
        compact_addr = re.sub(r"[^a-z0-9]", "", addr_lower)
        compact_name = re.sub(r"[^a-z0-9]", "", name_lower)
        compact_tags = [re.sub(r"[^a-z0-9]", "", t) for t in tags]

        if resolved_host_lower and addr_lower == resolved_host_lower:
            score += 120
        elif addr_lower == clean_q or s["id"] == clean_q or addr_lower == q_host:
            score += 100
        elif compact_q and (compact_q == compact_id or compact_q == compact_addr):
            score += 95
        elif addr_lower.startswith(clean_q) or s["id"].startswith(clean_q):
            score += 85
        elif compact_q and (compact_addr.startswith(compact_q) or compact_id.startswith(compact_q)):
            score += 80
        elif name_lower.startswith(clean_q) or (compact_q and compact_name.startswith(compact_q)):
            score += 70
        elif clean_q in addr_lower or clean_q in name_lower:
            score += 55
        elif compact_q and (compact_q in compact_addr or compact_q in compact_name):
            score += 50
        elif any(clean_q in t for t in tags) or (compact_q and any(compact_q in ct for ct in compact_tags)):
            score += 40
        elif clean_q in cat_lower:
            score += 30

        if score > 0:
            item = {
                "name": s["name"],
                "address": s["address"],
                "category": s["category"],
                "category_label": s.get("category_label", s["category"]),
                "icon": s["icon"],
                "description": s.get("description", ""),
            }
            scored_results.append((score, item))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored_results[:limit]]

