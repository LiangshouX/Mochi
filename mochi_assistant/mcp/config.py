"""
* Time      : 2026/7/2 10:43
* Author    : LiangshouX
* File      : config.py
* Function  : [ L2-数据模型 ] MCP 配置模型
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field


class AuthType(str, Enum):
    """认证类型枚举"""
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"


class MCPServerConfig(BaseModel):
    """MCP Server 配置模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="MCP Server显示的名称")
    url: str = Field(description="MCP Server的URL")
    auth_type: AuthType = Field(default=AuthType.API_KEY, description="认证类型")
    auth_config: Dict[str, Any] = Field(default_factory=dict, description="认证配置")
    enabled: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()


class MCPConfig(BaseModel):
    """ MCP  配置容器 """
    serves: Dict[str, MCPServerConfig] = Field(default_factory=dict)

    def add_server(self, server: MCPServerConfig) -> None:
        self.serves[server.id] = server

    def remove_server(self, server_id: str) -> bool:
        if server_id in self.serves:
            del self.serves[server_id]
            return True
        return False

    def get_server(self, server_id: str) -> Optional[MCPServerConfig]:
        return self.serves.get(server_id)

    def list_servers(self, enabled_only: bool = False) -> List[MCPServerConfig]:
        servers = list(self.serves.values())
        if enabled_only:
            servers = [s for s in servers if s.enabled]
        return servers
