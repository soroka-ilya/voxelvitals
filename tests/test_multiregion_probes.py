"""Tests for R2: Multi-Region Latency Probes.

Covers Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases) for:
- 3 geographic locations: Moscow (MSK), Frankfurt (FRA), Helsinki (HEL)
- Regional routing models (CIS, North America, Western/Central Europe)
- Status pill classifications (excellent, good, fair)
- Edge latencies, boundary clamping, and address parsing
"""

import pytest
from app.services.probes_service import get_multi_region_probes


# ==============================================================================
# Tier 1: Feature Coverage (R2 Core Behaviors)
# ==============================================================================


def test_probes_returns_exactly_three_geographic_regions():
    """Verify probe service returns exactly 3 probes for MSK, FRA, and HEL."""
    probes = get_multi_region_probes("mc.hypixel.net", base_latency_ms=25.0)
    assert len(probes) == 3

    codes = [p["code"] for p in probes]
    assert codes == ["MSK", "FRA", "HEL"]


def test_probes_cis_regional_routing_hierarchy():
    """Verify CIS servers (.ru/.su/reallyworld) place Moscow at base and Frankfurt highest."""
    # Test with .ru domain
    probes_ru = get_multi_region_probes("play.reallyworld.ru", base_latency_ms=15.0)
    p_map = {p["code"]: p["latency_ms"] for p in probes_ru}

    # Moscow is closest (base), Helsinki is intermediate, Frankfurt is farthest
    assert p_map["MSK"] == 15.0
    assert p_map["HEL"] > p_map["MSK"]
    assert p_map["FRA"] > p_map["HEL"]

    # Test with CIS keyword
    probes_cis = get_multi_region_probes("mc.vimeworld.net", base_latency_ms=10.0)
    p_map_cis = {p["code"]: p["latency_ms"] for p in probes_cis}
    assert p_map_cis["MSK"] == 10.0
    assert p_map_cis["FRA"] > p_map_cis["MSK"]


def test_probes_us_regional_routing_hierarchy():
    """Verify North American servers (hypixel, 2b2t) apply transatlantic routing."""
    probes = get_multi_region_probes("mc.hypixel.net", base_latency_ms=120.0)
    p_map = {p["code"]: p["latency_ms"] for p in probes}

    # Transatlantic Frankfurt is at least 85ms
    assert p_map["FRA"] >= 85.0
    # Helsinki is slightly higher than Frankfurt
    assert p_map["HEL"] > p_map["FRA"]
    # Moscow reports the measured ground-truth ping
    assert p_map["MSK"] == 120.0


def test_probes_eu_regional_routing_hierarchy():
    """Verify European servers (cubecraft, generic EU) place Frankfurt lowest."""
    probes = get_multi_region_probes("play.cubecraft.net", base_latency_ms=50.0)
    p_map = {p["code"]: p["latency_ms"] for p in probes}

    # Frankfurt is the primary European routing hub
    assert p_map["FRA"] < p_map["MSK"]
    assert p_map["HEL"] > p_map["FRA"]


def test_probes_status_tier_classification():
    """Verify latency tier status labels: excellent (<45ms), good (45-89ms), fair (>=90ms)."""
    # Low ping server (<45ms)
    probes_fast = get_multi_region_probes("fast.ru", base_latency_ms=10.0)
    msk_fast = next(p for p in probes_fast if p["code"] == "MSK")
    assert msk_fast["status"] == "excellent"

    # Moderate ping server (45-89ms)
    probes_mod = get_multi_region_probes("mod.ru", base_latency_ms=55.0)
    msk_mod = next(p for p in probes_mod if p["code"] == "MSK")
    assert msk_mod["status"] == "good"

    # High ping server (>=90ms)
    probes_slow = get_multi_region_probes("slow.ru", base_latency_ms=130.0)
    msk_slow = next(p for p in probes_slow if p["code"] == "MSK")
    assert msk_slow["status"] == "fair"


def test_probes_city_and_country_names_in_russian():
    """Verify city and country names are properly formatted in Russian with flags."""
    probes = get_multi_region_probes("any.server.org", base_latency_ms=30.0)
    probe_dict = {p["code"]: p for p in probes}

    msk = probe_dict["MSK"]
    assert msk["city"] == "Москва"
    assert msk["country"] == "Россия"
    assert msk["flag"] == "🇷🇺"

    fra = probe_dict["FRA"]
    assert fra["city"] == "Франкфурт"
    assert fra["country"] == "Германия"
    assert fra["flag"] == "🇩🇪"

    hel = probe_dict["HEL"]
    assert hel["city"] == "Хельсинки"
    assert hel["country"] == "Финляндия"
    assert hel["flag"] == "🇫🇮"


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Clamping, Extreme Values, Normalization)
# ==============================================================================


def test_probes_minimum_latency_clamping():
    """Verify base latency of 0.0 or negative is safely clamped to >= 1.0ms."""
    probes_zero = get_multi_region_probes("zero.ru", base_latency_ms=0.0)
    for p in probes_zero:
        assert p["latency_ms"] >= 1.0

    probes_neg = get_multi_region_probes("neg.ru", base_latency_ms=-25.0)
    for p in probes_neg:
        assert p["latency_ms"] >= 1.0


def test_probes_extreme_high_latency_handling():
    """Verify extreme base latency (2500ms) handles cleanly without overflow."""
    probes = get_multi_region_probes("laggy.network.com", base_latency_ms=2500.0)
    assert len(probes) == 3
    msk = next(p for p in probes if p["code"] == "MSK")
    assert msk["latency_ms"] == 2500.0
    assert msk["status"] == "fair"
    for p in probes:
        assert p["latency_ms"] > 0
        assert isinstance(p["latency_ms"], float)



def test_probes_address_case_insensitivity_and_whitespace():
    """Verify address parsing handles mixed case and whitespace for routing triggers."""
    p1 = get_multi_region_probes("mc.hypixel.net", base_latency_ms=100.0)
    p2 = get_multi_region_probes("  MC.HYPIXEL.NET \n", base_latency_ms=100.0)

    assert [p["latency_ms"] for p in p1] == [p["latency_ms"] for p in p2]
    assert [p["status"] for p in p1] == [p["status"] for p in p2]


def test_probes_bedrock_edition_support():
    """Verify Bedrock edition argument is accepted without error."""
    probes_bedrock = get_multi_region_probes(
        "geo.hivebedrock.network", base_latency_ms=40.0, edition="bedrock"
    )
    assert len(probes_bedrock) == 3
    assert all(p["latency_ms"] > 0 for p in probes_bedrock)


def test_probes_required_keys_and_types():
    """Verify every probe entry adheres to the strict schema contract."""
    probes = get_multi_region_probes("test.server.io", base_latency_ms=30.0)
    required_keys = {"code", "city", "country", "flag", "latency_ms", "status"}

    for p in probes:
        assert set(p.keys()) == required_keys
        assert isinstance(p["code"], str)
        assert isinstance(p["city"], str)
        assert isinstance(p["country"], str)
        assert isinstance(p["flag"], str)
        assert isinstance(p["latency_ms"], (float, int))
        assert isinstance(p["status"], str)
        assert p["status"] in {"excellent", "good", "fair"}


def test_probes_empty_or_unknown_tld_fallback():
    """Verify address with unusual TLD defaults gracefully to the European routing model."""
    probes_unknown = get_multi_region_probes("play.customdomain.xyz", base_latency_ms=45.0)
    assert len(probes_unknown) == 3

    # Unknown defaults to Western / Central Europe model (Frankfurt lowest)
    p_map = {p["code"]: p["latency_ms"] for p in probes_unknown}
    assert p_map["FRA"] < p_map["MSK"]
