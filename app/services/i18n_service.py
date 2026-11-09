"""VoxelVitals Core i18n Service.

Provides multi-language translation management across Russian (ru), English (en),
Chinese Simplified (zh), and German (de) with RFC 9110 Accept-Language parsing,
strict detection precedence (Cookie -> Query -> Header -> Default), coroutine-safe
ContextVar request isolation, and automatic fallback to Russian.
"""

from contextvars import ContextVar
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("voxelvitals.i18n")

SUPPORTED_LANGUAGES: Tuple[str, ...] = ("ru", "en", "zh", "de")
DEFAULT_LANGUAGE: str = "ru"

LANGUAGE_METADATA: Dict[str, Dict[str, str]] = {
    "ru": {"code": "ru", "name": "Русский", "flag": "🇷🇺", "locale": "ru_RU"},
    "en": {"code": "en", "name": "English", "flag": "🇬🇧", "locale": "en_US"},
    "zh": {"code": "zh", "name": "简体中文", "flag": "🇨🇳", "locale": "zh_CN"},
    "de": {"code": "de", "name": "Deutsch", "flag": "🇩🇪", "locale": "de_DE"},
}

LOCALES_DIR: Path = Path(__file__).resolve().parent.parent / "locales"

current_lang_var: ContextVar[str] = ContextVar("current_lang", default=DEFAULT_LANGUAGE)
_TRANSLATIONS: Dict[str, Dict[str, Any]] = {}


def load_translations(locales_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load JSON translation dictionaries for all supported languages into memory cache."""
    global _TRANSLATIONS
    target_dir = Path(locales_dir) if locales_dir else LOCALES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    loaded: Dict[str, Dict[str, Any]] = {}
    for code in SUPPORTED_LANGUAGES:
        file_path = target_dir / f"{code}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    loaded[code] = json.load(f)
            except Exception as exc:
                logger.error(f"Failed to load translation file {file_path}: {exc}")
                loaded[code] = {}
        else:
            loaded[code] = {}

    _TRANSLATIONS = loaded
    return _TRANSLATIONS


def parse_accept_language(header: Optional[str]) -> Optional[str]:
    """Parse HTTP Accept-Language header taking RFC 9110 q-values and sub-tags into account.

    Examples:
        - "en-US,en;q=0.9" -> "en"
        - "zh-CN,zh;q=0.9,ru;q=0.5" -> "zh"
        - "fr-FR,es;q=0.9" -> None (unsupported)
    """
    if not header or not isinstance(header, str):
        return None

    candidates = []
    for item in header.split(","):
        parts = item.strip().split(";")
        tag = parts[0].strip().lower()
        if not tag or tag == "*":
            continue

        q = 1.0
        for p in parts[1:]:
            p_strip = p.strip().lower()
            if p_strip.startswith("q="):
                try:
                    q = float(p_strip[2:])
                except ValueError:
                    q = 0.0

        primary_tag = tag.split("-")[0]
        candidates.append((q, primary_tag))

    # Sort descending by quality factor; stable sort preserves relative client order
    candidates.sort(key=lambda x: x[0], reverse=True)
    for q_val, lang in candidates:
        if q_val > 0.0 and lang in SUPPORTED_LANGUAGES:
            return lang

    return None


def get_request_language(request: Any) -> str:
    """Determine effective language following strict precedence:

    1. Cookie: `vv_lang`
    2. Query parameter: `?lang=`
    3. HTTP Header: `Accept-Language`
    4. Default: `ru`
    """
    # 1. Cookie (vv_lang)
    try:
        cookies = getattr(request, "cookies", None)
        if cookies and hasattr(cookies, "get"):
            cookie_lang = cookies.get("vv_lang")
            if cookie_lang and isinstance(cookie_lang, str) and cookie_lang.lower() in SUPPORTED_LANGUAGES:
                return cookie_lang.lower()
    except Exception:
        pass

    # 2. Query param (?lang=)
    try:
        query_params = getattr(request, "query_params", None)
        if query_params and hasattr(query_params, "get"):
            query_lang = query_params.get("lang")
            if query_lang and isinstance(query_lang, str) and query_lang.lower() in SUPPORTED_LANGUAGES:
                return query_lang.lower()
    except Exception:
        pass

    # 3. Accept-Language header
    try:
        headers = getattr(request, "headers", None)
        if headers and hasattr(headers, "get"):
            accept_lang = headers.get("accept-language")
            if accept_lang:
                detected = parse_accept_language(accept_lang)
                if detected:
                    return detected
    except Exception:
        pass

    # 4. Default fallback
    return DEFAULT_LANGUAGE


def get_current_lang() -> str:
    """Return active language code from contextvar."""
    return current_lang_var.get()


def set_current_lang(lang: str) -> None:
    """Set active language code in contextvar if supported."""
    if lang and isinstance(lang, str):
        lang_lower = lang.lower()
        if lang_lower in SUPPORTED_LANGUAGES:
            current_lang_var.set(lang_lower)


def _lookup_key(data: Dict[str, Any], key: str) -> Optional[str]:
    """Retrieve translated string supporting direct key or dot-notation traversal."""
    if not isinstance(data, dict):
        return None

    # Direct key lookup
    if key in data and isinstance(data[key], str):
        return data[key]

    # Nested dot-notation traversal
    curr: Any = data
    for part in key.split("."):
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif isinstance(curr, dict) and part == "server" and "server_detail" in curr:
            curr = curr["server_detail"]
        elif isinstance(curr, dict) and part == "server_detail" and "server" in curr:
            curr = curr["server"]
        else:
            return None

    return curr if isinstance(curr, str) else None


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """Translate key for target language with automatic fallback to Russian ('ru').

    Supports dot-notation keys (e.g. 'hero.title'), format kwargs (e.g. count=5),
    and custom 'default' keyword argument.
    """
    eff_lang = (lang or get_current_lang()).lower()
    if eff_lang not in SUPPORTED_LANGUAGES:
        eff_lang = DEFAULT_LANGUAGE

    target_dict = _TRANSLATIONS.get(eff_lang, {})
    val = _lookup_key(target_dict, key)

    # Automatic fallback to Russian
    if val is None and eff_lang != DEFAULT_LANGUAGE:
        ru_dict = _TRANSLATIONS.get(DEFAULT_LANGUAGE, {})
        val = _lookup_key(ru_dict, key)

    # Fallback to default or raw key
    if val is None:
        val = kwargs.get("default", key)

    # Keyword formatting
    if kwargs and isinstance(val, str):
        try:
            format_kwargs = {k: v for k, v in kwargs.items() if k != "default"}
            if format_kwargs:
                return val.format(**format_kwargs)
            return val
        except (KeyError, ValueError, IndexError):
            return val

    return val


# Pre-load translations on module import
load_translations()
