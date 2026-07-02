"""
* Time      : 2026/7/2 10:15
* Author    : LiangshouX
* File      : long_term.py
* Function  : 长期记忆实现与管理
"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

from mochi_agent.logging_config import get_logger
from mochi_agent.storage import JSONStore
from mochi_agent.storage.workspace import get_workspace_subdir

logger = get_logger(__name__)


class Memory(BaseModel):
    """ 长期记忆实例模型 """
    key: str = Field(description="记忆唯一key")
    value: str = Field(description="记忆内容")
    tags: List[str] = Field(default=list, description="标签")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


class LongTermMemory:
    """长期记忆（跨会话持久化）"""

    def __init__(self, storage_dir: Optional[Path] = None):
        """初始化长期记忆。

        Args:
            storage_dir: 记忆存储目录
        """
        if storage_dir is None:
            storage_dir = get_workspace_subdir("memory/long_term")

        self.storage = JSONStore(storage_dir)
        self._memories: Dict[str, Memory] = {}
        self._load_all()

    def _load_all(self) -> None:
        """从存储中加载所有记忆"""
        data = self.storage.get("memories", {})
        for key, value in data.items():
            try:
                self._memories[key] = Memory(**value)
            except Exception as e:
                logger.error(f"Failed to load memory {key}: {e}")

    def _save_all(self) -> None:
        """将所有记忆保存到存储"""
        data = {key: memory.model_dump() for key, memory in self._memories.items()}
        self.storage.set("memories", data)

    def set(
            self,
            key: str,
            value: str,
            tags: Optional[List[str]] = None
    ) -> Memory:
        """设置记忆值。

        Args:
            key: 记忆键
            value: 记忆值
            tags: 可选标签

        Returns:
            创建或更新的记忆对象
        """
        now = datetime.now()

        if key in self._memories:
            memory = self._memories[key]
            memory.value = value
            memory.tags = tags or memory.tags
            memory.updated_at = now
        else:
            memory = Memory(key=key, value=value, tags=tags or [])
            self._memories[key] = memory

        self._save_all()
        logger.info(f"Set memory: {key}")
        return memory

    def get(self, key: str) -> Optional[str]:
        """获取记忆值。

        Args:
            key: 记忆键

        Returns:
            记忆值或 None
        """
        memory = self._memories.get(key)
        return memory.value if memory else None

    def get_memory(self, key: str) -> Optional[Memory]:
        """获取完整的记忆对象。

        Args:
            key: 记忆键

        Returns:
            记忆对象或 None
        """
        return self._memories.get(key)

    def delete(self, key: str) -> bool:
        """删除记忆。

        Args:
            key: 记忆键

        Returns:
            如果已删除则返回 True
        """
        if key in self._memories:
            del self._memories[key]
            self._save_all()
            logger.info(f"Deleted memory: {key}")
            return True
        return False

    def list_keys(self) -> List[str]:
        """列出所有记忆键。

        Returns:
            键列表
        """
        return sorted(self._memories.keys())

    def list_memories(self) -> List[Memory]:
        """列出所有记忆。

        Returns:
            记忆列表
        """
        return sorted(self._memories.values(), key=lambda m: m.updated_at, reverse=True)

    def search(
            self,
            query: Optional[str] = None,
            tags: Optional[List[str]] = None
    ) -> List[Memory]:
        """搜索记忆。

        Args:
            query: 可选的文本查询（搜索键和值）
            tags: 可选的标签过滤

        Returns:
            匹配的记忆列表
        """
        results = list(self._memories.values())

        # Filter by tags
        if tags:
            results = [m for m in results if any(t in m.tags for t in tags)]

        # Filter by query
        if query:
            query_lower = query.lower()
            results = [
                m for m in results
                if query_lower in m.key.lower() or query_lower in m.value.lower()
            ]

        return sorted(results, key=lambda m: m.updated_at, reverse=True)

    def add_tag(self, key: str, tag: str) -> bool:
        """为记忆添加标签。

        Args:
            key: 记忆键
            tag: 要添加的标签

        Returns:
            如果已添加则返回 True
        """
        memory = self._memories.get(key)
        if not memory:
            return False

        if tag not in memory.tags:
            memory.tags.append(tag)
            memory.updated_at = datetime.now()
            self._save_all()

        return True

    def remove_tag(self, key: str, tag: str) -> bool:
        """从记忆中移除标签。

        Args:
            key: 记忆键
            tag: 要移除的标签

        Returns:
            如果已移除则返回 True
        """
        memory = self._memories.get(key)
        if not memory:
            return False

        if tag in memory.tags:
            memory.tags.remove(tag)
            memory.updated_at = datetime.now()
            self._save_all()

        return True

    def clear(self) -> None:
        """清除所有记忆"""
        self._memories.clear()
        self._save_all()
        logger.info("Cleared all long-term memories")

    def search_by_tag(self, tag: str) -> List[Memory]:
        """按标签搜索记忆。

        Args:
            tag: 要搜索的标签

        Returns:
            匹配的记忆列表
        """
        return self.search(tags=[tag])


class MemoryManager:
    """记忆管理器包装器，用于 CLI 兼容性"""

    def __init__(self, storage_dir: Optional[Path] = None):
        """初始化记忆管理器。

        Args:
            storage_dir: 记忆存储目录
        """
        self._memory = LongTermMemory(storage_dir)

    def set_memory(self, key: str, value: str, tags: Optional[List[str]] = None) -> Memory:
        """设置记忆。

        Args:
            key: 记忆键
            value: 记忆值
            tags: 可选标签

        Returns:
            创建或更新的记忆对象
        """
        return self._memory.set(key, value, tags)

    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """通过 ID（键）获取记忆。

        Args:
            memory_id: 记忆 ID（键）

        Returns:
            记忆对象或 None
        """
        return self._memory.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆。

        Args:
            memory_id: 记忆 ID（键）

        Returns:
            如果已删除则返回 True
        """
        return self._memory.delete(memory_id)

    def list_memories(self) -> List[Dict[str, Any]]:
        """列出所有记忆。

        Returns:
            记忆信息列表
        """
        memories = self._memory.list_memories()
        return [
            {
                "id": m.key,
                "key": m.key,
                "value": m.value,
                "tags": m.tags,
                "created_at": m.created_at.isoformat(),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in memories
        ]

    def search_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """按标签搜索记忆。

        Args:
            tag: 要搜索的标签

        Returns:
            匹配的记忆列表
        """
        memories = self._memory.search_by_tag(tag)
        return [
            {
                "id": m.key,
                "key": m.key,
                "value": m.value,
                "tags": m.tags,
            }
            for m in memories
        ]
