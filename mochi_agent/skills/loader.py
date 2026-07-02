"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : loader.py
* Function  : SKILL 文件加载器 — 从 ~/.mochi/skills/ 加载技能定义
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from mochi_agent.logging_config import get_logger
from mochi_agent.skills.schema import Skill, ActionType, SkillAction
from mochi_agent.storage.workspace import get_workspace_subdir

logger = get_logger(__name__)

# YAML frontmatter 分隔符
FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def parse_skill_file(file_path: Path) -> Optional[Skill]:
    """解析单个 SKILL 文件

    Args:
        file_path: SKILL 文件路径（.md）

    Returns:
        Skill 对象，解析失败返回 None
    """
    try:
        content = file_path.read_text(encoding='utf-8')

        # 提取 YAML frontmatter
        match = FRONTMATTER_PATTERN.match(content)
        if not match:
            logger.warning(f"SKILL 文件缺少 YAML frontmatter: {file_path}")
            return None

        yaml_content = match.group(1)
        metadata = yaml.safe_load(yaml_content)

        if not isinstance(metadata, dict):
            logger.warning(f"SKILL 文件 frontmatter 格式错误: {file_path}")
            return None

        # 提取正文（指令模板）
        body = content[match.end():].strip()

        # 构建 SkillAction
        action_data = metadata.get('action', {})
        action = SkillAction(
            type=ActionType(action_data.get('type', 'response')),
            params=action_data.get('params', {}),
        )

        # 构建 Skill
        skill = Skill(
            id=metadata.get('name', file_path.stem),
            command=metadata.get('command', f"/{file_path.stem}"),
            name=metadata.get('name', file_path.stem),
            description=metadata.get('description', ''),
            action=action,
            enabled=metadata.get('enabled', True),
        )

        # 附加正文和参数定义
        skill._body = body  # type: ignore
        skill._parameters = metadata.get('parameters', [])  # type: ignore

        # 验证
        is_valid, error_msg = skill.validate_skill()
        if not is_valid:
            logger.warning(f"SKILL 文件验证失败 {file_path}: {error_msg}")
            # 仍然返回，但标记为禁用
            skill.enabled = False

        return skill

    except yaml.YAMLError as e:
        logger.error(f"SKILL 文件 YAML 解析错误 {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"SKILL 文件加载失败 {file_path}: {e}")
        return None


class SkillRegistry:
    """技能注册表 — 管理所有已加载的技能"""

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir is None:
            skills_dir = get_workspace_subdir("skills")

        self.skills_dir = skills_dir
        self._skills: Dict[str, Skill] = {}

    def load_all(self) -> int:
        """加载所有 SKILL 文件

        Returns:
            成功加载的技能数量
        """
        if not self.skills_dir.exists():
            logger.info(f"技能目录不存在: {self.skills_dir}")
            return 0

        self._skills.clear()
        loaded = 0

        for file_path in self.skills_dir.glob("*.md"):
            skill = parse_skill_file(file_path)
            if skill:
                self._skills[skill.command] = skill
                loaded += 1
                logger.info(f"加载技能: {skill.command} — {skill.name}")

        logger.info(f"共加载 {loaded} 个技能")
        return loaded

    def get(self, command: str) -> Optional[Skill]:
        """通过命令名获取技能

        Args:
            command: 斜杠命令（如 /commit）
        """
        return self._skills.get(command)

    def list_skills(self, enabled_only: bool = True) -> List[Skill]:
        """列出所有技能

        Args:
            enabled_only: 是否只返回启用的技能
        """
        skills = list(self._skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return skills

    def reload(self) -> int:
        """重新加载所有技能"""
        return self.load_all()
