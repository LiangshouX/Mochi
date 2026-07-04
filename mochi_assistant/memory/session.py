"""
* Time      : 2026/7/2 8:56
* Author    : LiangshouX
* File      : session.py
* Function  : 短期记忆 / Session管理
"""
import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from mochi_assistant.logging_config import get_logger
from mochi_assistant.storage.workspace import get_workspace_subdir

logger = get_logger(__name__)


class MessageRole(str, Enum):
    """角色类型枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """
    对话消息模型
    """
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建消息（兼容 JSONL 加载）"""
        role = data.get("role", "user")
        if isinstance(role, str):
            role = MessageRole(role)
        ts = data.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = datetime.now()
        return cls(role=role, content=data.get("content", ""), timestamp=ts or datetime.now())


class Session(BaseModel):
    """
    对话Session模型
    """
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = Field(default=None)
    messages: list[Message] = Field(default_factory=list)
    create_at: datetime = Field(default_factory=datetime.now)
    update_at: datetime = Field(default_factory=datetime.now)

    def add_message(self, role: MessageRole, content: str) -> Message:
        """
        向session中添加消息
        """
        message = Message(role=role, content=content)
        self.messages.append(message)
        self.update_at = datetime.now()
        return message

    def get_last_message(self) -> Message:
        """
        获取最后一条消息
        """
        return self.messages[-1]

    def get_messages(self, limit: Optional[int] = None) -> list[Message]:
        """ 从session中获取message

        Args:
            limit: 限制最近几条消息的数量
        """
        if limit is None:
            return self.messages
        return self.messages[-limit:]


class ShortTermMemory:
    """ 基于 Session 的短期记忆实现 — JSONL 格式存储 """

    def __init__(self, storage_dir: Optional[Path] = None):
        """ 初始化
        Args:
             storage_dir: Session 的存储地址
        """
        if storage_dir is None:
            storage_dir = get_workspace_subdir("memory/sessions")

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._current_session: Optional[Session] = None

    def _session_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.storage_dir / f"{session_id}.jsonl"

    def create_session(self) -> Session:
        """ 创建一个新的 Session """
        session = Session()
        self._current_session = session
        logger.info(f"创建新 Session {session.session_id}")
        return session

    def get_or_create_session(self, session_id: Optional[str] = None) -> Session:
        """ 获取当前 Session，如果没有则创建一个新的 Session """
        if session_id:
            session = self.load_session(session_id)
            if session:
                self._current_session = session
                return session
        if self._current_session is not None:
            return self._current_session
        return self.create_session()

    def load_session(self, session_id: str) -> Optional[Session]:
        """ 从 JSONL 文件加载 Session """
        file_path = self._session_path(session_id)
        if not file_path.exists():
            return None

        try:
            session = Session(session_id=session_id)
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("_meta"):
                        session.create_at = obj.get("create_at", session.create_at)
                        session.update_at = obj.get("update_at", session.update_at)
                        session.name = obj.get("name")
                    else:
                        session.messages.append(Message.from_dict(obj))
            logger.info(f"加载 Session {session.session_id[:8]}...")
            return session
        except Exception as e:
            logger.error(f"加载 Session {session_id} 失败: {e}")
            return None

    def save_session(self, session: Session) -> None:
        """保存 Session 到 JSONL 文件（每条消息一行 JSON）"""
        file_path = self._session_path(session.session_id)
        try:
            lines = []
            # 第一行: 元数据
            meta = {
                "_meta": True,
                "session_id": session.session_id,
                "name": session.name,
                "create_at": session.create_at.isoformat() if isinstance(session.create_at, datetime) else str(session.create_at),
                "update_at": datetime.now().isoformat(),
            }
            lines.append(json.dumps(meta, ensure_ascii=False))
            # 后续行: 每条消息
            for msg in session.messages:
                d = {
                    "role": msg.role.value if isinstance(msg.role, MessageRole) else msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat() if isinstance(msg.timestamp, datetime) else str(msg.timestamp),
                }
                lines.append(json.dumps(d, ensure_ascii=False))

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            logger.debug(f"会话已保存: {session.session_id[:8]}...")
        except Exception as e:
            logger.error(f"保存会话失败: {e}")

    def delete_session(self, session_id: str) -> None:
        """ 删除 Session """
        file_path = self._session_path(session_id)
        if file_path.exists():
            file_path.unlink()

    def list_sessions(self) -> list[str]:
        """ 列出所有 Session ID """
        if not self.storage_dir.exists():
            return []
        return sorted(
            [f.stem for f in self.storage_dir.glob("*.jsonl")],
            reverse=True,
        )

    def add_message(
            self,
            role: MessageRole,
            content: str,
            session_id: Optional[str] = None
    ) -> Message:
        """ 向 Session 中添加消息 """
        if session_id:
            session = self.get_or_create_session(session_id)
            if not session:
                session = self.create_session()
        else:
            if not self._current_session:
                self._current_session = self.create_session()
            session = self._current_session

        message = session.add_message(role, content)
        self.save_session(session)
        return message

    def get_messages(
            self,
            session_id: Optional[str] = None,
            limit: Optional[int] = None
    ) -> List[Message]:
        """ 从 Session 中获取 Message """
        if session_id:
            session = self.load_session(session_id)
        else:
            session = self._current_session

        if not session:
            return []

        return session.get_messages(limit)

    def clear_session(self, session_id: Optional[str] = None) -> bool:
        if session_id:
            session = self.load_session(session_id)
        else:
            session = self._current_session

        if not session:
            return False

        session.messages.clear()
        session.update_at = datetime.now()
        self.save_session(session)
        return True

    def get_current_session(self) -> Optional[Session]:
        return self._current_session


class SessionManager:
    """会话管理器包装器,用于 CLI 兼容性"""

    def __init__(self, storage_dir: Optional[Path] = None):
        """初始化会话管理器。

        Args:
            storage_dir: 会话存储目录
        """
        self._memory = ShortTermMemory(storage_dir)

    def create_session(self, name: Optional[str] = None) -> Session:
        """创建新会话。

        Args:
            name: 可选的会话名称

        Returns:
            新创建的会话
        """
        session = self._memory.create_session()
        if name:
            session.name = name  # type: ignore
        self._memory.save_session(session)
        return session

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话。

        Returns:
            会话信息列表
        """
        session_ids = self._memory.list_sessions()
        sessions = []
        for sid in session_ids:
            session = self._memory.load_session(sid)
            if session:
                sessions.append({
                    "id": session.session_id,
                    "name": getattr(session, "name", None),
                    "created_at": str(session.create_at),
                    "message_count": len(session.messages),
                })
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        """通过 ID 获取会话。

        Args:
            session_id: 会话 ID

        Returns:
            会话对象或 None
        """
        return self._memory.load_session(session_id)

    def add_message(
            self,
            role: MessageRole,
            content: str,
            session_id: Optional[str] = None
    ) -> Message:
        """向会话添加消息。

        Args:
            role: 消息角色
            content: 消息内容
            session_id: 可选的会话 ID

        Returns:
            创建的消息对象
        """
        return self._memory.add_message(role, content, session_id)

    def get_messages(
            self,
            session_id: Optional[str] = None,
            limit: Optional[int] = None
    ) -> List[Message]:
        """从会话中获取消息。

        Args:
            session_id: 可选的会话 ID
            limit: 最近消息的可选数量限制

        Returns:
            消息列表
        """
        return self._memory.get_messages(session_id, limit)
