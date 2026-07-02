"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : client.py
* Function  : MCP 客户端 — 连接 MCP 服务器，发现和调用工具
"""
import asyncio
from typing import Any, Dict, List, Optional

from mochi_agent.logging_config import get_logger
from mochi_agent.mcp.config import MCPServerConfig, MCPConfig
from mochi_agent.mcp.auth import MCPAuthFactory
from mochi_agent.tools import ToolRegistry, get_tool_registry

logger = get_logger(__name__)


class MCPClient:
    """MCP 客户端 — 管理与 MCP 服务器的连接"""

    def __init__(self, mcp_config: MCPConfig, tool_registry: Optional[ToolRegistry] = None):
        self.mcp_config = mcp_config
        self.tool_registry = tool_registry or get_tool_registry()
        self._sessions: Dict[str, Any] = {}  # server_id → session
        self._connected: Dict[str, bool] = {}

    async def connect_all(self) -> None:
        """连接所有启用的 MCP 服务器"""
        servers = self.mcp_config.list_servers(enabled_only=True)
        if not servers:
            logger.info("没有配置 MCP 服务器")
            return

        logger.info(f"正在连接 {len(servers)} 个 MCP 服务器...")

        for server in servers:
            try:
                await self.connect_server(server)
            except Exception as e:
                logger.error(f"连接 MCP 服务器 '{server.name}' 失败: {e}")
                self._connected[server.id] = False

    async def connect_server(self, server: MCPServerConfig) -> None:
        """连接单个 MCP 服务器

        Args:
            server: MCP 服务器配置
        """
        logger.info(f"正在连接 MCP 服务器: {server.name} ({server.url})")

        try:
            # 尝试使用 mcp SDK
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            # 获取认证头
            auth_headers = {}
            if server.auth_type and server.auth_type != "none":
                from mochi_agent.mcp.config import AuthType
                auth_obj = MCPAuthFactory.get_auth(
                    AuthType(server.auth_type),
                    server.auth_config,
                )
                if auth_obj:
                    # 从 AuthBase 对象提取 headers
                    import requests as req
                    prepared = req.Request('GET', 'http://dummy').prepare()
                    auth_obj(prepared)
                    auth_headers = dict(prepared.headers)

            # 建立 SSE 连接
            transport = await sse_client(server.url, headers=auth_headers)
            read_stream, write_stream = transport
            session = ClientSession(read_stream, write_stream)
            await session.initialize()

            self._sessions[server.id] = session
            self._connected[server.id] = True

            # 发现并注册工具
            await self._discover_tools(server, session)

            logger.info(f"MCP 服务器 '{server.name}' 连接成功")

        except ImportError:
            logger.warning(
                f"未安装 mcp SDK，跳过 MCP 服务器 '{server.name}'。"
                f"请运行: pip install mcp"
            )
            self._connected[server.id] = False
        except Exception as e:
            logger.error(f"连接 MCP 服务器 '{server.name}' 失败: {e}")
            self._connected[server.id] = False
            raise

    async def _discover_tools(self, server: MCPServerConfig, session: Any) -> None:
        """从 MCP 服务器发现并注册工具

        Args:
            server: 服务器配置
            session: MCP 会话
        """
        try:
            tools_response = await session.list_tools()
            tools = tools_response.tools if hasattr(tools_response, 'tools') else []

            for tool in tools:
                # 创建包装函数
                tool_name = f"mcp_{server.id}_{tool.name}"

                def make_handler(srv_id, tool_name, sess):
                    async def handler(**kwargs):
                        return await self.call_tool(srv_id, tool_name, kwargs)
                    return handler

                self.tool_registry.register(
                    name=tool_name,
                    description=f"[MCP:{server.name}] {tool.description}",
                    handler=make_handler(server.id, tool.name, session),
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    source=f"mcp:{server.id}",
                )

            logger.info(f"从 '{server.name}' 发现 {len(tools)} 个工具")

        except Exception as e:
            logger.error(f"从 '{server.name}' 发现工具失败: {e}")

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict) -> Any:
        """调用 MCP 服务器上的工具

        Args:
            server_id: 服务器 ID
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        session = self._sessions.get(server_id)
        if not session:
            raise ValueError(f"MCP 服务器 '{server_id}' 未连接")

        logger.info(f"调用 MCP 工具: {server_id}/{tool_name}")
        result = await session.call_tool(tool_name, arguments)

        # 提取文本内容
        if hasattr(result, 'content'):
            contents = []
            for item in result.content:
                if hasattr(item, 'text'):
                    contents.append(item.text)
                else:
                    contents.append(str(item))
            return "\n".join(contents)

        return str(result)

    async def disconnect_all(self) -> None:
        """断开所有 MCP 服务器连接"""
        for server_id, session in self._sessions.items():
            try:
                if hasattr(session, 'close'):
                    await session.close()
                logger.info(f"断开 MCP 服务器: {server_id}")
            except Exception as e:
                logger.error(f"断开 MCP 服务器 '{server_id}' 失败: {e}")

        self._sessions.clear()
        self._connected.clear()

    def is_connected(self, server_id: str) -> bool:
        """检查服务器是否已连接"""
        return self._connected.get(server_id, False)

    def list_connected(self) -> List[str]:
        """列出已连接的服务器 ID"""
        return [sid for sid, connected in self._connected.items() if connected]
