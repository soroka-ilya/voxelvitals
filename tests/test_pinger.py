"""Unit tests for Minecraft server query engine."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.domain.models import PlayerSample, ServerStatus
from app.services.pinger import get_mock_server_status, query_server


def test_mock_server_status():
    """Verify mock status generation for online and offline states."""
    online = get_mock_server_status("test.server.net", is_online=True)
    assert online.is_online is True
    assert online.players_online == 1420
    assert len(online.players_sample) == 3
    assert "VOXELVITALS" in online.motd_plain
    assert "<span" in online.motd_html

    offline = get_mock_server_status("dead.server.net", is_online=False)
    assert offline.is_online is False
    assert offline.players_online == 0
    assert offline.error_message is not None


@pytest.mark.asyncio
async def test_query_server_mocked_success():
    """Verify query_server accurately maps mcstatus response object."""
    mock_status = MagicMock()
    mock_status.players.online = 850
    mock_status.players.max = 2000
    mock_player = MagicMock()
    mock_player.name = "Steve"
    mock_player.id = "12345678-1234-1234-1234-123456789abc"
    mock_status.players.sample = [mock_player]
    mock_status.version.name = "Spigot 1.21"
    mock_status.version.protocol = 767
    mock_status.latency = 22.4
    mock_status.motd.to_minecraft.return_value = "§aWelcome to our world"
    mock_status.icon = "data:image/png;base64,mockicon"

    mock_java_server = MagicMock()
    mock_java_server.async_status = AsyncMock(return_value=mock_status)

    with patch("app.services.pinger.JavaServer.async_lookup", AsyncMock(return_value=mock_java_server)):
        res = await query_server("hub.mocknode.net")
        assert res.is_online is True
        assert res.players_online == 850
        assert res.players_max == 2000
        assert len(res.players_sample) == 1
        assert res.players_sample[0].name == "Steve"
        assert res.latency_ms == 22.4
        assert res.icon_base64 == "data:image/png;base64,mockicon"


@pytest.mark.asyncio
async def test_query_server_offline_timeout():
    """Verify query_server captures network exceptions cleanly without raising."""
    with patch("app.services.pinger.JavaServer.async_lookup", side_effect=TimeoutError("Connection timed out")), \
         patch("app.services.pinger._query_http_fallback", AsyncMock(return_value=None)):
        res = await query_server("unreachable.node.internal")
        assert res.is_online is False
        assert res.players_online == 0


@pytest.mark.asyncio
async def test_query_server_tier2_fallback_success():
    """Verify query_server engages Tier-2 HTTP fallback when native TCP fails."""
    mock_fallback = ServerStatus(
        address="fallback.node.net",
        is_online=True,
        edition="java",
        players_online=999,
        players_max=2000,
        players_sample=[],
        version_name="Paper 1.21.1",
        latency_ms=28.0,
        motd_raw="Fallback MOTD",
        motd_html="<span>Fallback MOTD</span>",
        motd_plain="Fallback MOTD",
        icon_base64="data:image/png;base64,fallback_icon",
    )
    with patch("app.services.pinger.JavaServer.async_lookup", side_effect=Exception("DNS SRV SERVFAIL")), \
         patch("app.services.pinger._query_http_fallback", AsyncMock(return_value=mock_fallback)):
        res = await query_server("fallback.node.net")
        assert res.is_online is True
        assert res.players_online == 999
        assert res.icon_base64 == "data:image/png;base64,fallback_icon"

        assert res.error_message is None
