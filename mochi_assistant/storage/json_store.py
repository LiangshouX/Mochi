"""
* Time      : 2026/7/1 22:12
* Author    : LiangshouX
* File      : json_store.py
* Function  : JSON 文件存储实现
"""
import json
import sys
from json import JSONDecodeError

# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt
    def _lock_file(f, exclusive=True):
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    def _unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    def _lock_file(f, exclusive=True):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
from pathlib import Path
from typing import Any, List, Dict

from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)


class JSONStore:
    """Json 文件存储实现"""

    def __init__(self, base_dir: Path, create_dir: bool = True):
        """初始化

        Args:
            base_dir: Base Dir
            create_dir: 如果目录不存在，是否创建
        """
        self.base_dir = base_dir
        if create_dir:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, key: str, ext: str = ".json") -> Path:
        """根据 key 获取文件路径

        Args:
            key: Key
            ext: Extension
        """
        return self.base_dir / f"{key}{ext}"

    def get(self, key: str, default: Any = None) -> Any:
        """ 根据 key 获取具体的值

        Args:
            key: Storage key
            default: 如果 key 未找到时返回的默认值

        Returns:
            存储的值或者默认值
        """
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return default

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except JSONDecodeError as e:
            logger.error(f"JSON 文件 {file_path} 解析错误: {e}")
            return default
        except Exception as e:
            logger.error(f"读取 JSON 文件 {file_path} 失败: {e}")
            return default

    def set(self, key: str, value: Any) -> None:
        """ 依据 key 赋值 """
        file_path = self._get_file_path(key)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入 JSON 文件 {file_path} 失败: {e}")

    def delete(self, key: str) -> bool:
        """ 删除指定的 key """
        file_path = self._get_file_path(key)
        if file_path.exists():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"删除 JSON 文件 {file_path} 失败: {e}")
                return False
        return False

    def exists(self, key: str) -> bool:
        """ 判断指定的 key 是否存在 """
        return self._get_file_path(key).exists()

    def list_keys(self, pattern: str = "*.json") -> List[str]:
        """ 列出所有匹配的 key """
        if not self.base_dir.exists():
            return []

        keys = []
        for file_path in self.base_dir.glob(pattern):
            keys.append(file_path.stem)
        return sorted(keys)

    def get_all(self) -> Dict[str, Any]:
        """ 获取所有存储的键值对 """
        result = {}
        for key in self.list_keys():
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result


class ThreadSafeJSONStore(JSONStore):
    """ 线程安全的 JSON 文件存储实现 """

    def get(self, key: str, default: Any = None) -> Any:
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return default

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                _lock_file(f, exclusive=False)
                try:
                    return json.load(f)
                finally:
                    _unlock_file(f)
        except Exception as e:
            logger.error(f"JSON 文件 {file_path} 解析错误: {e}")
            return default

    def set(self, key: str, value: Any) -> None:
        file_path = self._get_file_path(key)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                _lock_file(f, exclusive=True)
                try:
                    json.dump(value, f, ensure_ascii=False, indent=2)
                finally:
                    _unlock_file(f)
        except Exception as e:
            logger.error(f"写入 JSON 文件 {file_path} 失败: {e}")
            raise
