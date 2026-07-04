"""
* Time      : 2026/7/2 11:00
* Author    : LiangshouX
* File      : schema.py
* Function  : [ L2 数据模型 ] Skill Schema 定义
"""

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """
    Skill Action 类型枚举
    """
    RESPONSE = "response"
    SHELL = "shell"
    HTTP = "http"
    FUNCTION = "function"


class SkillAction(BaseModel):
    """
    Skill Action 定义
    """
    type: ActionType = Field(description="Action 类型")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action 参数")


class Skill(BaseModel):
    """
    Skill 定义
    """
    id: str = Field(description="Skill 唯一标识符（文件名）")
    command: str = Field(description="Skill 触发命令，如/my-skill")
    name: str = Field(description="Skill 名称")
    description: str = Field(description="Skill 描述")
    action: SkillAction = Field(description="Skill Action")
    enabled: bool = Field(default=True, description="Skill 是否启用")

    def validate_skill(self) -> Tuple[bool, Optional[str]]:
        """
        校验 Skill 是否合法
        """
        # RULE1: Command 必须以/开头
        if not self.command.startswith("/"):
            return False, "Command 必须以/开头"

        # RULE2: Action 必须合法
        if self.action.type not in ActionType:
            return False, "无效的Action"

        # RULE3: 基于Action类型校验参数
        if self.action.type == ActionType.RESPONSE:
            if "message" not in self.action.params:
                return False, "RESPONSE Action 必须包含message参数"
        elif self.action.type == ActionType.SHELL:
            if "command" not in self.action.params:
                return False, "SHELL Action 必须包含command参数"
        elif self.action.type == ActionType.HTTP:
            if "url" not in self.action.params:
                return False, "HTTP Action 必须包含url参数"

        return True, None
