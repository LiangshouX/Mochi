"""
* Time      : 2026/7/1 21:46
* Author    : LiangshouX
* File      : workspace.py
* Function  : Mochi Agent Workspace 初始化与管理相关功能
"""
from pathlib import Path
from typing import Optional

from mochi_agent.logging_config import get_logger

logger = get_logger(__name__)

# 默认目录结构
DEFAULT_DIRS = [
    "config",
    "memory/sessions",
    "memory/long_term",
    "skills",
    "logs",
]


def get_workspace_dir() -> Path:
    """获取 Mochi Agent 工作区目录

    Returns:
        ~/.mochi/
    """
    home = Path.home()
    workspace = home / ".mochi"
    return workspace


def ini_workspace(workspace_dir: Optional[Path] = None, force: bool = False) -> Path:
    """初始化 Mochi Agent 工作区

    Args:
        workspace_dir: 工作区目录，默认为 ~/.mochi/
        force: 是否强制初始化

    Returns:
        初始化后的工作区地址
    """
    if workspace_dir is None:
        workspace_dir = get_workspace_dir()

    if workspace_dir.exists() and not force:
        logger.info(f"工作区 {workspace_dir} 已经存在")
        return workspace_dir

    # 创建目录结构
    for subdir in DEFAULT_DIRS:
        dir_path = workspace_dir / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"创建目录 {dir_path}")

    # 如果配置文件不存在，创建默认配置文件
    _create_default_configs(workspace_dir)

    logger.info(f"初始化工作区 {workspace_dir} 成功")
    return workspace_dir


def _create_default_configs(workspace_dir: Path):
    """创建所有默认的配置文件"""
    import json

    config_dir = workspace_dir / "config"

    # 默认 Agent 配置
    agent_config = config_dir / "agent.json"
    if not agent_config.exists():
        default_config = {
            "agent": {
                "model": "deepseek-v4-pro",
                "temperature": 0.7,
                "max_tokens": 4096
            },
            "security": {
                "allowed_directories": [str(Path.home())],
                "dangerous_commands": ["rm -rf", "del /f /s /q", "format", "mkfs"],
                "confirm_dangerous": True
            },
            "mcp": {
                "servers": {}
            }
        }

        with open(agent_config, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.debug(f"创建默认 Agent 配置文件 {agent_config}")

    # MCP Server 配置
    mcp_config = config_dir / "mcp_servers.json"
    if not mcp_config.exists():
        default_config = {
            "servers": {}
        }
        with open(mcp_config, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.debug(f"创建默认 MCP 配置文件 {mcp_config}")

    # 安全配置
    security_config = config_dir / "security.json"
    if not security_config.exists():
        default_config = {
            "allowed_directories": [str(Path.home())],
            "dangerous_commands": ["rm -rf", "del /f /s /q", "format", "mkfs"],
            "confirm_dangerous": True
        }
        with open(security_config, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        logger.debug(f"创建默认安全配置文件 {security_config}")


def ensure_workspace(workspace_dir: Optional[Path] = None) -> Path:
    """ 确保工作区目录存在，若不存在，则初始化 """
    if workspace_dir is None:
        workspace_dir = get_workspace_dir()

    if not workspace_dir.exists():
        ini_workspace(workspace_dir)

    return workspace_dir


def get_workspace_subdir(subdir: str) -> Path:
    """ 获取工作区下的子目录 """
    workspace = ensure_workspace()
    subdir_path = workspace / subdir
    subdir_path.mkdir(parents=True, exist_ok=True)
    return subdir_path
