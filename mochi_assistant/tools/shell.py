"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : shell.py
* Function  : 内置 Shell 命令执行工具
"""
import subprocess
from typing import Optional

from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)

# 默认危险命令列表
DEFAULT_BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "del /f /s /q C:\\",
    "format",
    "mkfs",
    ":(){:|:&};:",  # fork bomb
]


def shell_exec(
    command: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
    blocked_commands: Optional[list[str]] = None,
) -> str:
    """执行 shell 命令

    Args:
        command: 要执行的命令
        timeout: 超时时间（秒）
        working_dir: 工作目录
        blocked_commands: 被阻止的命令列表

    Returns:
        命令输出

    Raises:
        ValueError: 命令被阻止
        RuntimeError: 执行失败或超时
    """
    # 检查危险命令
    blocked = blocked_commands or DEFAULT_BLOCKED_COMMANDS
    command_lower = command.lower().strip()

    for blocked_cmd in blocked:
        if blocked_cmd.lower() in command_lower:
            raise ValueError(f"命令被阻止（危险操作）: {command}")

    logger.info(f"执行 shell 命令: {command}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        return output.strip() or "(无输出)"

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"命令执行超时（{timeout}秒）")
    except Exception as e:
        raise RuntimeError(f"命令执行失败: {e}")


def register_shell_tools(registry, security_config=None) -> None:
    """注册 shell 工具到工具注册表

    Args:
        registry: ToolRegistry 实例
        security_config: 可选的安全配置
    """
    blocked = DEFAULT_BLOCKED_COMMANDS
    if security_config and hasattr(security_config, 'dangerous_commands'):
        blocked = security_config.dangerous_commands

    def shell_handler(command: str) -> str:
        return shell_exec(command, blocked_commands=blocked)

    registry.register(
        name="shell_exec",
        description="执行 shell 命令并返回输出",
        handler=shell_handler,
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
            },
            "required": ["command"],
        },
    )
