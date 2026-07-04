"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : file_ops.py
* Function  : 内置文件操作工具
"""
from pathlib import Path
from typing import List

from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)


def file_read(path: str) -> str:
    """读取文件内容

    Args:
        path: 文件路径

    Returns:
        文件内容文本

    Raises:
        FileNotFoundError: 文件不存在
        PermissionError: 无权限读取
    """
    file_path = Path(path).expanduser().resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not file_path.is_file():
        raise ValueError(f"路径不是文件: {path}")

    # 限制文件大小（防止读取超大文件）
    size = file_path.stat().st_size
    if size > 10 * 1024 * 1024:  # 10MB
        raise ValueError(f"文件过大 ({size / 1024 / 1024:.1f}MB)，超过 10MB 限制")

    logger.info(f"读取文件: {file_path}")
    return file_path.read_text(encoding='utf-8', errors='replace')


def file_write(path: str, content: str) -> str:
    """写入文件内容

    Args:
        path: 文件路径
        content: 要写入的内容

    Returns:
        成功消息

    Raises:
        PermissionError: 无权限写入
    """
    file_path = Path(path).expanduser().resolve()

    # 确保父目录存在
    file_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"写入文件: {file_path}")
    file_path.write_text(content, encoding='utf-8')

    return f"已写入文件: {file_path} ({len(content)} 字符)"


def file_list(directory: str = ".") -> str:
    """列出目录内容

    Args:
        directory: 目录路径

    Returns:
        目录内容列表

    Raises:
        FileNotFoundError: 目录不存在
    """
    dir_path = Path(directory).expanduser().resolve()

    if not dir_path.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    if not dir_path.is_dir():
        raise ValueError(f"路径不是目录: {directory}")

    logger.info(f"列出目录: {dir_path}")
    entries = []

    for item in sorted(dir_path.iterdir()):
        if item.is_dir():
            entries.append(f"📁 {item.name}/")
        else:
            size = item.stat().st_size
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / 1024 / 1024:.1f}MB"
            entries.append(f"📄 {item.name} ({size_str})")

    return "\n".join(entries) if entries else "(空目录)"


def file_search(directory: str = ".", pattern: str = "*") -> str:
    """搜索文件

    Args:
        directory: 搜索目录
        pattern: glob 模式（如 *.py, **/*.txt）

    Returns:
        匹配的文件列表

    Raises:
        FileNotFoundError: 目录不存在
    """
    dir_path = Path(directory).expanduser().resolve()

    if not dir_path.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    logger.info(f"搜索文件: {dir_path} / {pattern}")
    matches = list(dir_path.glob(pattern))

    # 限制结果数量
    if len(matches) > 100:
        matches = matches[:100]
        truncated = True
    else:
        truncated = False

    lines = [str(m.relative_to(dir_path)) for m in matches if m.is_file()]
    result = "\n".join(lines) if lines else "(无匹配文件)"

    if truncated:
        result += f"\n... (结果已截断，共 {len(matches)} 个匹配)"

    return result


def register_file_tools(registry) -> None:
    """注册文件操作工具到工具注册表

    Args:
        registry: ToolRegistry 实例
    """
    registry.register(
        name="file_read",
        description="读取指定路径的文件内容",
        handler=file_read,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"],
        },
    )

    registry.register(
        name="file_write",
        description="将内容写入指定路径的文件",
        handler=file_write,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
            },
            "required": ["path", "content"],
        },
    )

    registry.register(
        name="file_list",
        description="列出指定目录的文件和子目录",
        handler=file_list,
        input_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "目录路径", "default": "."}
            },
        },
    )

    registry.register(
        name="file_search",
        description="使用 glob 模式搜索文件",
        handler=file_search,
        input_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "搜索目录", "default": "."},
                "pattern": {"type": "string", "description": "glob 模式", "default": "*"},
            },
        },
    )
