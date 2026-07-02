"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : executor.py
* Function  : SKILL 执行器 — 根据 ActionType 执行技能动作
"""
import re
import subprocess
from typing import Any, Dict, Optional

import aiohttp

from mochi_agent.logging_config import get_logger
from mochi_agent.skills.schema import ActionType, Skill

logger = get_logger(__name__)

# 模板变量正则 {{variable}}
TEMPLATE_VAR_PATTERN = re.compile(r'\{\{(\w+)\}\}')


def substitute_template(template: str, variables: Dict[str, str]) -> str:
    """替换模板中的 {{variable}} 变量

    Args:
        template: 包含模板变量的文本
        variables: 变量名 → 值的映射

    Returns:
        替换后的文本
    """
    def replacer(match):
        var_name = match.group(1)
        return variables.get(var_name, match.group(0))

    return TEMPLATE_VAR_PATTERN.sub(replacer, template)


def execute_skill(
    skill: Skill,
    arguments: Optional[Dict[str, str]] = None,
    body: str = "",
) -> str:
    """执行技能

    Args:
        skill: 技能定义
        arguments: 用户提供的参数
        body: 技能正文（指令模板）

    Returns:
        执行结果文本

    Raises:
        ValueError: 缺少必需参数
        RuntimeError: 执行失败
    """
    args = arguments or {}

    # 验证必需参数
    parameters = getattr(skill, '_parameters', [])
    for param in parameters:
        if param.get('required', False) and param['name'] not in args:
            default = param.get('default')
            if default is not None:
                args[param['name']] = str(default)
            else:
                raise ValueError(f"缺少必需参数: {param['name']}")

    action = skill.action

    if action.type == ActionType.RESPONSE:
        return _execute_response(body, args)

    elif action.type == ActionType.SHELL:
        return _execute_shell(action.params, args)

    elif action.type == ActionType.HTTP:
        return _execute_http(action.params, args)

    elif action.type == ActionType.FUNCTION:
        return _execute_function(action.params, args)

    else:
        raise ValueError(f"不支持的 Action 类型: {action.type}")


def _execute_response(body: str, args: Dict[str, str]) -> str:
    """执行 RESPONSE 类型 — 返回替换后的正文"""
    return substitute_template(body, args)


def _execute_shell(params: dict, args: Dict[str, str]) -> str:
    """执行 SHELL 类型 — 运行 shell 命令"""
    command = params.get('command', '')
    if not command:
        raise ValueError("SHELL 动作缺少 'command' 参数")

    # 替换模板变量
    command = substitute_template(command, args)

    working_dir = params.get('working_dir', '.')

    logger.info(f"执行 shell 命令: {command}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=working_dir,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        return output.strip() or "(无输出)"

    except subprocess.TimeoutExpired:
        raise RuntimeError("命令执行超时（60秒）")
    except Exception as e:
        raise RuntimeError(f"命令执行失败: {e}")


def _execute_http(params: dict, args: Dict[str, str]) -> str:
    """执行 HTTP 类型 — 发送 HTTP 请求（同步）"""
    import requests

    method = params.get('method', 'GET').upper()
    url = substitute_template(params.get('url', ''), args)
    headers = {
        k: substitute_template(v, args)
        for k, v in params.get('headers', {}).items()
    }
    body = params.get('body')

    if not url:
        raise ValueError("HTTP 动作缺少 'url' 参数")

    logger.info(f"执行 HTTP 请求: {method} {url}")
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body,
            timeout=30,
        )
        return f"[{response.status_code}] {response.text}"
    except Exception as e:
        raise RuntimeError(f"HTTP 请求失败: {e}")


def _execute_function(params: dict, args: Dict[str, str]) -> str:
    """执行 FUNCTION 类型 — 调用注册的 Python 函数"""
    func_name = params.get('function_name', '')
    if not func_name:
        raise ValueError("FUNCTION 动作缺少 'function_name' 参数")

    # TODO: 实现函数注册表和调用
    raise NotImplementedError(f"FUNCTION 类型执行暂未实现: {func_name}")
