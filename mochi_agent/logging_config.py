"""
* Time      : 2026/7/1 20:40
* Author    : LiangshouX
* File      : logging_config.py
* Function  : L0 基础设施层，仅依赖标准库，实现日志配置
"""
import logging
import sys
from pathlib import Path
from typing import Optional

_default_logger: Optional[logging.Logger] = None


def setup_logging(
        level: int = logging.INFO,
        log_file: Optional[Path] = None,
        format_string: Optional[str] = None
):
    """设置 logging 配置

    Args:
        level:          日志级别， 默认为 INFO
        log_file:       日志文件的存储路径
        format_string:  自定义格式化日志
    """
    if format_string is None:
        format_string = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"

    # 创建 formatter
    formatter = logging.Formatter(format_string)

    # root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 移除已经存在的 handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # 如果指定了 日志文件，设置 File Handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def init_default_logging(workspace_dir: Optional[Path] = None):
    """初始化应用的默认 logging

    Args:
        workspace_dir: 日志文件存储的默认工作区路径
    """
    global _default_logger

    log_file = None
    if workspace_dir:
        log_dir = workspace_dir / "logs"
        log_file = log_dir / "mochi.log"

    _default_logger = setup_logging(log_file=log_file)
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
