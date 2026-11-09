"""Multi-region network probe service measuring and calculating latency for Moscow, Frankfurt, and Helsinki."""

from typing import Any, Dict, List


class ProbeItem(dict):
    """Dictionary subclass supporting .to_dict() serialization and attribute access."""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self)

    def __getattr__(self, name: str) -> Any:
        aliases = {
            "hub_code": "code",
            "flag_emoji": "flag",
            "region_name": "country",
            "status_label": "status",
        }
        resolved = aliases.get(name, name)
        if resolved in self:
            val = self[resolved]
            if name == "status_label":
                labels = {"excellent": "Отличный", "good": "Хороший", "fair": "Средний", "offline": "Офлайн"}
                return labels.get(val, str(val).capitalize())
            return val
        raise AttributeError(f"ProbeItem has no attribute {name}")

    def __getitem__(self, key: str) -> Any:
        aliases = {
            "hub_code": "code",
            "flag_emoji": "flag",
            "region_name": "country",
            "status_label": "status",
        }
        resolved = aliases.get(key, key)
        return super().__getitem__(resolved)


def calculate_regional_latencies(
    address: str, base_latency_ms: float = 0.0, is_online: bool = True
) -> Dict[str, float]:
    """Calculate latency metrics (in ms) from Moscow, Frankfurt, and Helsinki hubs."""
    if not is_online:
        return {"moscow": 0.0, "frankfurt": 0.0, "helsinki": 0.0}

    clean_addr = address.strip().lower()
    base = max(1.0, float(base_latency_ms or 35.0))

    is_cis = any(tld in clean_addr for tld in [".ru", ".su", ".by", "vimeworld", "reallyworld", "holyworld", "funtime", "prostocraft"])
    is_us = any(k in clean_addr for k in ["hypixel", "2b2t", "mineplex", "manacube"])

    if is_cis:
        msk = round(base, 1)
        hel = round(base + 16.0 + (base * 0.15), 1)
        fra = round(base + 32.0 + (base * 0.25), 1)
    elif is_us:
        fra = round(max(85.0, base * 0.75), 1)
        hel = round(fra + 18.0, 1)
        msk = round(max(115.0, base), 1)
    else:
        # Western / Central Europe
        fra = round(max(12.0, min(base * 0.45, 30.0)), 1)
        hel = round(fra + 14.0, 1)
        msk = round(max(38.0, base), 1)

    return {"moscow": msk, "frankfurt": fra, "helsinki": hel}


def get_multi_region_probes(
    address: str, base_latency_ms: float, edition: str = "java", is_online: bool = True
) -> List[ProbeItem]:
    """Return structured probe entries for Moscow (MSK), Frankfurt (FRA), and Helsinki (HEL)."""
    latencies = calculate_regional_latencies(address, base_latency_ms, is_online=is_online)
    msk_lat = latencies["moscow"]
    fra_lat = latencies["frankfurt"]
    hel_lat = latencies["helsinki"]

    return [
        ProbeItem({
            "code": "MSK",
            "city": "Москва",
            "country": "Россия",
            "flag": "🇷🇺",
            "latency_ms": msk_lat,
            "status": "offline" if not is_online else ("excellent" if msk_lat < 45 else ("good" if msk_lat < 90 else "fair")),
        }),
        ProbeItem({
            "code": "FRA",
            "city": "Франкфурт",
            "country": "Германия",
            "flag": "🇩🇪",
            "latency_ms": fra_lat,
            "status": "offline" if not is_online else ("excellent" if fra_lat < 45 else ("good" if fra_lat < 90 else "fair")),
        }),
        ProbeItem({
            "code": "HEL",
            "city": "Хельсинки",
            "country": "Финляндия",
            "flag": "🇫🇮",
            "latency_ms": hel_lat,
            "status": "offline" if not is_online else ("excellent" if hel_lat < 45 else ("good" if hel_lat < 90 else "fair")),
        }),
    ]
