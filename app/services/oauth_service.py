"""OAuth 2.0 service for Google and Microsoft (Xbox Live / Mojang API) authentication."""

import logging
from typing import Any, Dict, Optional
import httpx
from app.config import settings

logger = logging.getLogger("voxelvitals.oauth")


class GoogleOAuthService:
    """Google OAuth 2.0 integration helper."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Google OAuth credentials are provided."""
        return bool(settings.google_client_id and settings.google_client_secret)

    @classmethod
    def get_auth_url(cls, state: str, redirect_uri: Optional[str] = None) -> str:
        """Build Google consent screen URL."""
        eff_redirect = redirect_uri or settings.google_redirect_uri or f"{settings.base_url}/api/auth/google/callback"
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": eff_redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        query_str = "&".join(f"{k}={httpx.URL('', params={k: v}).query.decode()}" for k, v in params.items())
        return f"{cls.AUTH_URL}?{query_str}"

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchange authorization code for user profile."""
        eff_redirect = redirect_uri or settings.google_redirect_uri or f"{settings.base_url}/api/auth/google/callback"
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_res = await client.post(
                cls.TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": eff_redirect,
                },
            )
            token_res.raise_for_status()
            token_data = token_res.json()
            access_token = token_data.get("access_token")

            userinfo_res = await client.get(
                cls.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_res.raise_for_status()
            info = userinfo_res.json()

            return {
                "provider": "google",
                "provider_id": str(info.get("id")),
                "email": info.get("email", ""),
                "name": info.get("name", ""),
                "avatar_url": info.get("picture", ""),
                "mc_nickname": "",
                "is_verified_license": False,
            }


class MicrosoftOAuthService:
    """Microsoft OAuth 2.0 integration with Xbox Live and Mojang API profile verification."""

    AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
    TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    XBL_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
    XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
    MINECRAFT_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
    MINECRAFT_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
    GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Microsoft OAuth credentials are provided."""
        return bool(settings.microsoft_client_id and settings.microsoft_client_secret)

    @classmethod
    def get_auth_url(cls, state: str, redirect_uri: Optional[str] = None) -> str:
        """Build Microsoft consent screen URL."""
        eff_redirect = redirect_uri or settings.microsoft_redirect_uri or f"{settings.base_url}/api/auth/microsoft/callback"
        params = {
            "client_id": settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": eff_redirect,
            "scope": "XboxLive.signin offline_access openid profile email",
            "state": state,
            "prompt": "select_account",
        }
        query_str = "&".join(f"{k}={httpx.URL('', params={k: v}).query.decode()}" for k, v in params.items())
        return f"{cls.AUTH_URL}?{query_str}"

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """Exchange code and query Minecraft license profile."""
        eff_redirect = redirect_uri or settings.microsoft_redirect_uri or f"{settings.base_url}/api/auth/microsoft/callback"
        async with httpx.AsyncClient(timeout=12.0) as client:
            token_res = await client.post(
                cls.TOKEN_URL,
                data={
                    "client_id": settings.microsoft_client_id,
                    "client_secret": settings.microsoft_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": eff_redirect,
                },
            )
            token_res.raise_for_status()
            token_data = token_res.json()
            ms_access_token = token_data.get("access_token")

            # Try to fetch Minecraft Profile via Xbox Live chain
            mc_profile = await cls._fetch_minecraft_profile(client, ms_access_token)
            if mc_profile:
                return mc_profile

            # Fallback to standard Microsoft Graph userinfo
            graph_res = await client.get(
                cls.GRAPH_ME_URL,
                headers={"Authorization": f"Bearer {ms_access_token}"},
            )
            if graph_res.status_code == 200:
                g_data = graph_res.json()
                return {
                    "provider": "microsoft",
                    "provider_id": str(g_data.get("id")),
                    "email": g_data.get("mail") or g_data.get("userPrincipalName", ""),
                    "name": g_data.get("displayName", ""),
                    "avatar_url": "",
                    "mc_nickname": "",
                    "is_verified_license": False,
                }

            return {
                "provider": "microsoft",
                "provider_id": "ms_" + code[:16],
                "email": "",
                "name": "Microsoft User",
                "avatar_url": "",
                "mc_nickname": "",
                "is_verified_license": False,
            }

    @classmethod
    async def _fetch_minecraft_profile(cls, client: httpx.AsyncClient, ms_token: str) -> Optional[Dict[str, Any]]:
        """Authenticate through Xbox Live and query official Mojang profile."""
        try:
            # 1. Xbox Live User Authentication
            xbl_res = await client.post(
                cls.XBL_AUTH_URL,
                json={
                    "Properties": {
                        "AuthMethod": "RPS",
                        "SiteName": "user.auth.xboxlive.com",
                        "RpsTicket": f"d={ms_token}",
                    },
                    "RelyingParty": "http://auth.xboxlive.com",
                    "TokenType": "JWT",
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if xbl_res.status_code != 200:
                return None
            xbl_data = xbl_res.json()
            xbl_token = xbl_data["Token"]
            uhs = xbl_data["DisplayClaims"]["xui"][0]["uhs"]

            # 2. XSTS Token Request
            xsts_res = await client.post(
                cls.XSTS_AUTH_URL,
                json={
                    "Properties": {
                        "SandboxId": "RETAIL",
                        "UserTokens": [xbl_token],
                    },
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT",
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if xsts_res.status_code != 200:
                return None
            xsts_token = xsts_res.json()["Token"]

            # 3. Mojang Login With Xbox
            mc_login_res = await client.post(
                cls.MINECRAFT_LOGIN_URL,
                json={"identityToken": f"XBL3.0 x={uhs};{xsts_token}"},
                headers={"Content-Type": "application/json"},
            )
            if mc_login_res.status_code != 200:
                return None
            mc_token = mc_login_res.json()["access_token"]

            # 4. Fetch Minecraft Profile
            prof_res = await client.get(
                cls.MINECRAFT_PROFILE_URL,
                headers={"Authorization": f"Bearer {mc_token}"},
            )
            if prof_res.status_code != 200:
                return None
            prof = prof_res.json()
            mc_uuid = prof.get("id", "")
            mc_name = prof.get("name", "")

            return {
                "provider": "microsoft",
                "provider_id": mc_uuid or f"xbl_{uhs}",
                "email": "",
                "name": mc_name,
                "avatar_url": f"https://mc-heads.net/avatar/{mc_uuid}/48" if mc_uuid else "",
                "mc_nickname": mc_name,
                "is_verified_license": True,
            }
        except Exception as exc:
            logger.warning("Minecraft profile fetch failed: %s", exc)
            return None
