"""
* Time      : 2026/7/2 11:27
* Author    : LiangshouX
* File      : auth.py
* Function  : MCP 认证处理器
"""

from typing import Any, Dict, Optional

import requests
from requests.auth import AuthBase

from mochi_assistant.logging_config import get_logger
from mochi_assistant.mcp.config import AuthType

logger = get_logger(__name__)


class BaseMCPAuthHandler:
    """ MCP 认证处理器基类 """

    def get_auth(self, auth_config: Dict[str, Any]) -> Optional[AuthBase]:
        raise NotImplementedError


class APIKeyAuthHandler(BaseMCPAuthHandler):
    """API Key 认证处理器"""

    def get_auth(self, auth_config: Dict[str, Any]) -> Optional[AuthBase]:
        """获取 API Key 认证"""
        api_key = auth_config.get("api_key")
        if not api_key:
            logger.warning("认证配置中未提供 API Key")
            return None

        header_name = auth_config.get("header_name", "X-API-Key")

        class APIKeyAuth(AuthBase):
            def __call__(self, r):
                r.headers[header_name] = api_key
                return r

        return APIKeyAuth()


class BearerTokenAuthHandler(BaseMCPAuthHandler):
    """Bearer Token 认证处理器"""

    def get_auth(self, auth_config: Dict[str, Any]) -> Optional[AuthBase]:
        """获取 Bearer Token 认证"""
        token = auth_config.get("token")
        if not token:
            logger.warning("认证配置中未提供 Token")
            return None

        class BearerAuth(AuthBase):
            def __call__(self, r):
                r.headers["Authorization"] = f"Bearer {token}"
                return r

        return BearerAuth()


class OAuth2AuthHandler(BaseMCPAuthHandler):
    """OAuth 2.0 认证处理器"""

    def __init__(self):
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    def get_auth(self, auth_config: Dict[str, Any]) -> Optional[AuthBase]:
        """获取 OAuth 2.0 认证"""
        client_id = auth_config.get("client_id")
        client_secret = auth_config.get("client_secret")
        token_url = auth_config.get("token_url")

        if not all([client_id, client_secret, token_url]):
            logger.warning("OAuth2 配置不完整")
            return None

        # 检查令牌缓存
        cache_key = f"{client_id}:{token_url}"
        cached = self._token_cache.get(cache_key)

        if cached and cached.get("expires_at", 0) > (__import__("time").time() + 60):
            token = cached["access_token"]
        else:
            # 请求新令牌
            try:
                response = requests.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    timeout=10,
                )
                response.raise_for_status()
                token_data = response.json()

                self._token_cache[cache_key] = {
                    "access_token": token_data["access_token"],
                    "expires_in": token_data.get("expires_in", 3600),
                    "expires_at": __import__("time").time() + token_data.get("expires_in", 3600),
                }
                token = token_data["access_token"]
            except Exception as e:
                logger.error(f"获取 OAuth2 令牌失败: {e}")
                return None

        class OAuth2Auth(AuthBase):
            def __call__(self, r):
                r.headers["Authorization"] = f"Bearer {token}"
                return r

        return OAuth2Auth()


class MCPAuthFactory:
    """用于创建 MCP 认证处理器的工厂类"""

    _handlers = {
        AuthType.API_KEY: APIKeyAuthHandler(),
        AuthType.BEARER: BearerTokenAuthHandler(),
        AuthType.OAUTH2: OAuth2AuthHandler(),
    }

    @classmethod
    def get_handler(cls, auth_type: AuthType) -> BaseMCPAuthHandler:
        """获取指定类型的认证处理器"""
        handler = cls._handlers.get(auth_type)
        if handler is None:
            raise ValueError(f"Unknown auth type: {auth_type}")
        return handler

    @classmethod
    def get_auth(cls, auth_type: AuthType, auth_config: Dict[str, Any]) -> Optional[AuthBase]:
        """获取指定类型的认证实例"""
        handler = cls.get_handler(auth_type)
        return handler.get_auth(auth_config)
