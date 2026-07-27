"""
* Time      : 2026/7/1 20:40
* Author    : LiangshouX
* File      : logging_config.py
* Function  : L0 基础设施层，仅依赖标准库，实现日志配置
"""
import logging
import sys
from pathlib import Path
from typing import List, Optional

_default_logger: Optional[logging.Logger] = None

# 默认压制的三方库 logger（避免 HTTP 请求等 INFO 日志刷屏）
DEFAULT_SILENT_LOGGERS = ["httpx", "openai", "httpcore", "urllib3", "langchain", "langsmith"]


def setup_logging(
        level: int = logging.INFO,
        console_level: int = logging.WARNING,
        log_file: Optional[Path] = None,
        format_string: Optional[str] = None,
        console_format_string: Optional[str] = None,
        silent_loggers: Optional[List[str]] = None,
):
    """设置 logging 配置

    Args:
        level:                 文件日志级别（root logger 级别），默认 INFO
        console_level:         控制台日志级别，默认 WARNING（避免刷屏）
        log_file:              日志文件的存储路径
        format_string:         文件日志格式
        console_format_string: 控制台日志格式（默认精简格式）
        silent_loggers:        需要压制到 WARNING 的三方库 logger 名称列表
    """
    if format_string is None:
        format_string = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
    if console_format_string is None:
        console_format_string = "[%(levelname)s] %(name)s: %(message)s"

    # 创建 formatter
    formatter = logging.Formatter(format_string)
    console_formatter = logging.Formatter(console_format_string)

    # root logger — 级别取两者中更低的，确保各 handler 都能收到所需事件
    root_logger = logging.getLogger()
    root_logger.setLevel(min(level, console_level))

    # 移除已经存在的 handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler — 输出到 stderr，带 formatter，默认仅 WARNING 以上
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 如果指定了 日志文件，设置 File Handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 压制三方库噪音 logger
    for name in (silent_loggers or []):
        logging.getLogger(name).setLevel(logging.WARNING)

    return root_logger


def init_default_logging(
        workspace_dir: Optional[Path] = None,
        console_level: int = logging.WARNING,
        file_level: int = logging.INFO,
):
    """初始化应用的默认 logging

    控制台默认仅显示 WARNING 及以上（-v 可提升至 INFO，-vv 至 DEBUG），
    完整 INFO 日志写入工作区 logs/mochi.log。

    Args:
        workspace_dir: 日志文件存储的默认工作区路径
        console_level: 控制台日志级别
        file_level:    文件日志级别
    """
    global _default_logger

    log_file = None
    if workspace_dir:
        log_dir = workspace_dir / "logs"
        log_file = log_dir / "mochi.log"

    _default_logger = setup_logging(
        level=file_level,
        console_level=console_level,
        log_file=log_file,
        silent_loggers=DEFAULT_SILENT_LOGGERS,
    )
    return _default_logger


def get_default_logger():
    """
    获取默认的 logger 实例
    """
    global _default_logger

    if _default_logger is None:
        pass
    return _default_logger


def get_logger(name: str) -> logging.Logger:
    """为某个特定的模块获取 logging 实例
    Args:
        name: Logger name (通常是 __name__)
    """
    return logging.getLogger(name)
