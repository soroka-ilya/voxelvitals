"""Telegram bot message processing and response generation for VoxelVitals."""

from typing import Any, Dict, Optional
from app.repository import ServerRepository
from app.services.alias_service import get_curated_catalog, is_bedrock_address, resolve_address
from app.services.pinger import query_server
from app.services.probes_service import get_multi_region_probes

repo = ServerRepository()


async def process_telegram_update(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process incoming Telegram update and return webhook response payload."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None

    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return None

    text = (message.get("text") or "").strip()
    if not text:
        return None

    parts = text.split()
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # Remove @botname suffix if present in group chats
    if "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ["/start", "/help"]:
        reply = (
            "👋 *Привет! Я официальный бот VoxelVitals* — платформы мониторинга и телеметрии серверов Minecraft.\n\n"
            "🎮 *Команды бота:*\n"
            "• `/status <ip>` — подробный статус сервера, онлайн, пинг и версия\n"
            "• `/ping <ip>` — замер задержки из 3 ключевых хабов (MSK, FRA, HEL)\n"
            "• `/record <ip>` — абсолютный рекорд онлайна сервера\n"
            "• `/top` — подборка популярных серверов\n\n"
            "🌐 Веб-версия: [voxelvitals.ru](https://voxelvitals.ru)"
        )
        return _make_tg_response(chat_id, reply)

    elif cmd == "/top":
        catalog = get_curated_catalog()[:6]
        lines = ["🏆 *Популярные серверы Minecraft:*", ""]
        for s in catalog:
            name = s.get("name", s["address"])
            badge = "🟣 Bedrock" if s.get("edition") == "bedrock" else "🟢 Java"
            lines.append(f"• *{name}* ({badge})\n  `{s['address']}` — [Открыть](https://voxelvitals.ru/server/{s['address']})")
        lines.append("\n_Для проверки используйте `/status <адрес>`_")
        return _make_tg_response(chat_id, "\n".join(lines))

    elif cmd in ["/status", "/s"]:
        if not arg:
            return _make_tg_response(
                chat_id,
                "⚠️ *Укажите адрес сервера!*\nПример: `/status hypixel` или `/status mc.hypixel.net`"
            )
        return await _handle_status_command(chat_id, arg)

    elif cmd in ["/ping", "/p"]:
        if not arg:
            return _make_tg_response(
                chat_id,
                "⚠️ *Укажите адрес сервера!*\nПример: `/ping hypixel` или `/ping vimeworld`"
            )
        return await _handle_ping_command(chat_id, arg)

    elif cmd in ["/record", "/peak"]:
        if not arg:
            return _make_tg_response(
                chat_id,
                "⚠️ *Укажите адрес сервера!*\nПример: `/record hypixel`"
            )
        return await _handle_record_command(chat_id, arg)

    else:
        # If user simply sent server IP without command
        if len(parts) == 1 and not cmd.startswith("/"):
            return await _handle_status_command(chat_id, cmd)

        return _make_tg_response(
            chat_id,
            "❓ Неизвестная команда. Введите `/help` для списка доступных команд или отправьте адрес сервера (например, `hypixel`)."
        )


async def _handle_status_command(chat_id: int, target: str) -> Dict[str, Any]:
    """Handle /status <address> request."""
    clean_addr = resolve_address(target)
    is_bedrock = is_bedrock_address(clean_addr)

    status = await query_server(clean_addr, is_bedrock=is_bedrock)
    peak = await repo.get_server_peak(clean_addr)

    status_icon = "🟢" if status.is_online else "🔴"
    status_label = "Online" if status.is_online else "Offline"
    edition_label = "Bedrock" if status.edition == "bedrock" else "Java"

    lines = [
        f"{status_icon} *{clean_addr}* ({edition_label})",
        f"📊 Статус: *{status_label}*",
    ]

    if status.is_online:
        lines.extend([
            f"👥 Онлайн: *{status.players_online:,}* / {status.players_max:,} игроков",
            f"⚡ Пинг: *{int(status.latency_ms)} ms*",
            f"📦 Версия: `{status.version_name}`",
        ])
        if peak:
            lines.append(f"🏆 Рекорд онлайна: *{peak['peak_players']:,}* ({peak['peak_date']})")
    else:
        lines.append(f"⚠️ Ошибка: _{status.error_message or 'Сервер недоступен'}_")

    lines.append(f"\n🔗 [Смотреть графики и телеметрию](https://voxelvitals.ru/server/{clean_addr})")
    return _make_tg_response(chat_id, "\n".join(lines))


async def _handle_ping_command(chat_id: int, target: str) -> Dict[str, Any]:
    """Handle /ping <address> multi-region probe request."""
    clean_addr = resolve_address(target)
    is_bedrock = is_bedrock_address(clean_addr)
    status = await query_server(clean_addr, is_bedrock=is_bedrock)

    probes = get_multi_region_probes(clean_addr, status.latency_ms, edition=status.edition, is_online=status.is_online)

    lines = [
        f"⚡ *Многоточечный замер пинга для `{clean_addr}`:*",
        "",
    ]
    for probe in probes:
        flag = probe.get("flag") or probe.get("flag_emoji", "🌐")
        city = probe.get("city", "Хаб")
        code = probe.get("code") or probe.get("hub_code", "HUB")
        latency = int(probe.get("latency_ms", 0))
        label = probe.get("status_label") or probe.get("status", "")
        lines.append(f"{flag} *{city} ({code})*: `{latency} ms` — _{label}_")

    lines.append(f"\n🌐 [Подробная аналитика](https://voxelvitals.ru/server/{clean_addr})")
    return _make_tg_response(chat_id, "\n".join(lines))


async def _handle_record_command(chat_id: int, target: str) -> Dict[str, Any]:
    """Handle /record <address> peak hall of fame request."""
    clean_addr = resolve_address(target)
    peak = await repo.get_server_peak(clean_addr)

    if peak:
        reply = (
            f"🏆 *Абсолютный рекорд онлайна для `{clean_addr}`:*\n\n"
            f"👑 Максимум: *{peak['peak_players']:,} игроков*\n"
            f"📅 Дата фиксации: *{peak['peak_date']}*\n\n"
            f"🌐 [Зал славы на VoxelVitals](https://voxelvitals.ru/server/{clean_addr})"
        )
    else:
        reply = f"ℹ️ Для сервера `{clean_addr}` рекорд ещё формируется на основе живой телеметрии."

    return _make_tg_response(chat_id, reply)


def _make_tg_response(chat_id: int, text: str) -> Dict[str, Any]:
    """Create standard Telegram Webhook JSON response."""
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
