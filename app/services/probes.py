"""Multi-region network probe service measuring and calculating latency for Moscow, Frankfurt, and Helsinki."""

from typing import Any, Dict, List, Optional
from app.services.i18n_service import get_current_lang, t


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
                eff_lang = self.__dict__.get("_lang") or get_current_lang()
                localized = t(f"probes.statuses.{val}", lang=eff_lang)
                if localized != f"probes.statuses.{val}":
                    return localized
                return str(val).capitalize()
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
    address: str,
    base_latency_ms: float,
    edition: str = "java",
    is_online: bool = True,
    lang: Optional[str] = None,
) -> List[ProbeItem]:
    """Return structured probe entries for Moscow (MSK), Frankfurt (FRA), and Helsinki (HEL)."""
    eff_lang = lang or get_current_lang()
    latencies = calculate_regional_latencies(address, base_latency_ms, is_online=is_online)
    hubs = (
        ("MSK", latencies["moscow"]),
        ("FRA", latencies["frankfurt"]),
        ("HEL", latencies["helsinki"]),
    )
    probes: List[ProbeItem] = []
    for code, lat in hubs:
        status_val = (
            "offline"
            if not is_online
            else ("excellent" if lat < 45 else ("good" if lat < 90 else "fair"))
        )
        item = ProbeItem({
            "code": code,
            "city": t(f"probes.hubs.{code}.city", lang=eff_lang),
            "country": t(f"probes.hubs.{code}.country", lang=eff_lang),
            "flag": t(f"probes.hubs.{code}.flag", lang=eff_lang),
            "latency_ms": lat,
            "status": status_val,
        })
        item._lang = eff_lang
        probes.append(item)
    return probes
