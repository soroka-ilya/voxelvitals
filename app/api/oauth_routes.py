"""OAuth 2.0 Web & API endpoints for Google and Microsoft (Xbox / Minecraft) login."""

import secrets
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from app.config import settings
from app.repository import ServerRepository
from app.services.auth_service import generate_session_token
from app.services.oauth_service import GoogleOAuthService, MicrosoftOAuthService

oauth_router = APIRouter(prefix="/api/auth", tags=["OAuth"])
repo = ServerRepository()


# =========================================================================
# Google OAuth 2.0 Endpoints
# =========================================================================

@oauth_router.get("/google/login")
async def google_login(request: Request, mock: bool = Query(False)):
    """Initiate Google OAuth 2.0 login flow."""
    state = secrets.token_urlsafe(16)
    if mock or not GoogleOAuthService.is_configured():
        if mock:
            # Dev / test mock flow
            response = RedirectResponse(
                url=f"/api/auth/google/callback?code=mock_google_code&state={state}&mock=true",
                status_code=302,
            )
            response.set_cookie("oauth_state_google", state, max_age=600, httponly=True, samesite="lax")
            return response
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth не настроен. Укажите GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в файле .env (см. OAUTH_SETUP.md).",
        )

    auth_url = GoogleOAuthService.get_auth_url(state)
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie("oauth_state_google", state, max_age=600, httponly=True, samesite="lax")
    return response


@oauth_router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    mock: bool = Query(False),
):
    """Handle callback from Google OAuth server."""
    if error:
        return RedirectResponse(url=f"/?auth_error=google_{error}", status_code=303)

    stored_state = request.cookies.get("oauth_state_google")
    if not mock and (not stored_state or stored_state != state):
        raise HTTPException(status_code=400, detail="Неверный параметр CSRF state при авторизации через Google.")

    if mock:
        user_info = {
            "provider": "google",
            "provider_id": "google_mock_12345",
            "email": "test_gamer@gmail.com",
            "name": "Google Gamer",
            "avatar_url": "https://lh3.googleusercontent.com/a/default-avatar",
            "mc_nickname": "",
            "is_verified_license": False,
        }
    else:
        try:
            user_info = await GoogleOAuthService.exchange_code(code)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка обмена токена Google: {exc}")

    # Create or link user in database
    user = await repo.create_or_link_oauth_user(
        provider="google",
        provider_id=user_info["provider_id"],
        email=user_info.get("email", ""),
        name=user_info.get("name", ""),
        mc_nickname=user_info.get("mc_nickname", ""),
        avatar_url=user_info.get("avatar_url", ""),
        is_verified_license=user_info.get("is_verified_license", False),
    )

    # Issue session token
    session_token = generate_session_token()
    await repo.create_session(session_token, user["id"])

    response = RedirectResponse(url="/?auth_success=google", status_code=303)
    response.set_cookie("session_token", session_token, max_age=30 * 86400, httponly=True, samesite="lax")
    response.delete_cookie("oauth_state_google")
    return response


# =========================================================================
# Microsoft / Xbox Live / Minecraft Endpoints
# =========================================================================

@oauth_router.get("/microsoft/login")
async def microsoft_login(request: Request, mock: bool = Query(False)):
    """Initiate Microsoft OAuth 2.0 login flow with Xbox Live."""
    state = secrets.token_urlsafe(16)
    if mock or not MicrosoftOAuthService.is_configured():
        if mock:
            response = RedirectResponse(
                url=f"/api/auth/microsoft/callback?code=mock_ms_code&state={state}&mock=true",
                status_code=302,
            )
            response.set_cookie("oauth_state_microsoft", state, max_age=600, httponly=True, samesite="lax")
            return response
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Microsoft OAuth не настроен. Укажите MICROSOFT_CLIENT_ID и MICROSOFT_CLIENT_SECRET в файле .env (см. OAUTH_SETUP.md).",
        )

    auth_url = MicrosoftOAuthService.get_auth_url(state)
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie("oauth_state_microsoft", state, max_age=600, httponly=True, samesite="lax")
    return response


@oauth_router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    mock: bool = Query(False),
):
    """Handle callback from Microsoft OAuth server."""
    if error:
        return RedirectResponse(url=f"/?auth_error=microsoft_{error}", status_code=303)

    stored_state = request.cookies.get("oauth_state_microsoft")
    if not mock and (not stored_state or stored_state != state):
        raise HTTPException(status_code=400, detail="Неверный параметр CSRF state при авторизации через Microsoft.")

    if mock:
        user_info = {
            "provider": "microsoft",
            "provider_id": "ms_mock_xbox_98765",
            "email": "steve_pro@outlook.com",
            "name": "Steve Pro",
            "avatar_url": "https://mc-heads.net/avatar/Steve/48",
            "mc_nickname": "Steve",
            "is_verified_license": True,
        }
    else:
        try:
            user_info = await MicrosoftOAuthService.exchange_code(code)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Ошибка обмена токена Microsoft: {exc}")

    # Create or link user in database
    user = await repo.create_or_link_oauth_user(
        provider="microsoft",
        provider_id=user_info["provider_id"],
        email=user_info.get("email", ""),
        name=user_info.get("name", ""),
        mc_nickname=user_info.get("mc_nickname", ""),
        avatar_url=user_info.get("avatar_url", ""),
        is_verified_license=user_info.get("is_verified_license", False),
    )

    # Issue session token
    session_token = generate_session_token()
    await repo.create_session(session_token, user["id"])

    response = RedirectResponse(url="/?auth_success=microsoft", status_code=303)
    response.set_cookie("session_token", session_token, max_age=30 * 86400, httponly=True, samesite="lax")
    response.delete_cookie("oauth_state_microsoft")
    return response
