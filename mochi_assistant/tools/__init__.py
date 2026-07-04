"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : __init__.py
* Function  : 工具注册表 — 管理内置工具和 MCP 工具
"""
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)


class ToolDef(BaseModel):
    """工具定义"""
    name: str = Field(description="工具唯一名称")
    description: str = Field(description="工具功能描述")
    input_schema: dict = Field(default_factory=dict, description="输入参数 JSON Schema")
    source: str = Field(default="builtin", description="来源: 'builtin' 或 MCP server ID")
    handler: Any = Field(default=None, exclude=True, description="执行函数")


class ToolRegistry:
    """工具注册表 — 管理所有可用工具"""

    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: Optional[dict] = None,
        source: str = "builtin",
    ) -> None:
        """注册一个工具

        Args:
            name: 工具唯一名称
            description: 工具功能描述
            handler: 执行函数
            input_schema: 输入参数 JSON Schema
            source: 来源标识
        """
        tool = ToolDef(
            name=name,
            description=description,
            input_schema=input_schema or {},
            source=source,
            handler=handler,
        )
        self._tools[name] = tool
        logger.info(f"注册工具: {name} (source={source})")

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"注销工具: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[ToolDef]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self, source: Optional[str] = None) -> List[ToolDef]:
        """列出所有工具

        Args:
            source: 可选的来源过滤
        """
        tools = list(self._tools.values())
        if source:
            tools = [t for t in tools if t.source == source]
        return tools

    def get_langchain_tools(self) -> list:
        """获取 LangChain 格式的工具列表（用于 agent 图）"""
        from langchain_core.tools import StructuredTool

        lc_tools = []
        for tool_def in self._tools.values():
            if tool_def.handler is None:
                continue

            # 创建 LangChain StructuredTool
            lc_tool = StructuredTool.from_function(
                func=tool_def.handler,
                name=tool_def.name,
                description=tool_def.description,
                args_schema=None,  # TODO: 从 input_schema 生成
            )
            lc_tools.append(lc_tool)
        return lc_tools

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """调用工具

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"工具不存在: {name}")

        if tool.handler is None:
            raise ValueError(f"工具 '{name}' 没有执行函数")

        logger.info(f"调用工具: {name}, 参数: {arguments}")
        try:
            result = tool.handler(**arguments)
            logger.info(f"工具 '{name}' 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 '{name}' 执行失败: {e}")
            raise


# 全局工具注册表实例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
