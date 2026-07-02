"""
* Time      : 2026/7/1 21:09
* Author    : LiangshouX
* File      : config.py
* Function  : L1 基础服务层， 项目的配置管理器
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

from mochi_agent.logging_config import get_logger

logger = get_logger(__name__)


class MochiConfig(BaseModel):
    """Mochi Agent 配置"""
    provider: str = Field(default="openai", description="LLM 供应商 (openai, anthropic, ollama, deepseek, zhipu)")
    model: str = Field(default="deepseek-v4-pro", description="模型名称")
    temperature: float = Field(default=0.7, description="LLM 温度")
    max_tokens: int = Field(default=4096, description="LLM 最大 token 长度")
    api_key: Optional[str] = Field(default=None, description="大模型供应商的 API KEY")
    base_url: Optional[str] = Field(default=None, description="自定义 API Base URL（留空使用默认值）")


class SecurityConfig(BaseModel):
    """安全配置"""
    allowed_directories: list[str] = Field(
        default_factory=lambda: [str(Path.home())],
        description="允许进行文件操作的目录"
    )
    dangerous_commands: list[str] = Field(
        default_factory=lambda: ["rm -rf", "del /f /s /q", "format", "mkfs"],
        description="需要用户确认的危险命令"
    )
    confirm_dangerous: bool = Field(default=True, description="是否需要用户确认危险命令")


class MCPConfig(BaseModel):
    """MCP Server配置"""
    servers: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="MCP Servers 配置"
    )


class Config(BaseModel):
    """聚合主配置"""
    mochi: MochiConfig = Field(default_factory=MochiConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class ConfigManager:
    """Mochi 配置管理器"""

    def __init__(self, workspace_dir: Path):
        """初始化"""
        self.workspace_dir = workspace_dir
        self.config_dir = workspace_dir / "config"
        self.config_file = self.config_dir / "config.json"
        self._config: Optional[Config] = None

    def ensure_config_dir(self):
        """ 确保配置文件地址存在 """
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> Config:
        """ 从配置文件中加载配置，不存在则创建默认模板 """
        if self._config is not None:
            return self._config

        self.ensure_config_dir()

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._config = Config(**data)
                logger.info(f"加载配置文件 {self.config_file} 成功!")
            except Exception as e:
                logger.error(f"加载配置文件 {self.config_file} 失败: {e}")
                self._config = Config()
        else:
            # 首次运行：创建默认配置模板
            self._config = Config()
            self._save_default_template()
            logger.info("配置文件不存在，已创建默认配置文件")

        return self._config

    def _save_default_template(self) -> None:
        """保存默认配置模板到 config.json"""
        template = {
            "mochi": {
                "provider": "openai",
                "model": "deepseek-chat",
                "temperature": 0.7,
                "max_tokens": 4096,
                "api_key": "sk-your-api-key-here",
                "base_url": None
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
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(template, f, ensure_ascii=False, indent=2)
            logger.info(f"已创建默认配置文件: {self.config_file}")
        except Exception as e:
            logger.error(f"创建默认配置文件失败: {e}")

    def save(self, config: Optional[Config] = None) -> bool:
        """将当前配置保存到 config.json

        Args:
            config: 要保存的配置对象，默认使用 self._config

        Returns:
            是否保存成功
        """
        if config is not None:
            self._config = config
        if self._config is None:
            return False

        self.ensure_config_dir()
        try:
            data = self._config.model_dump(mode='json')
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"配置已保存到 {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
