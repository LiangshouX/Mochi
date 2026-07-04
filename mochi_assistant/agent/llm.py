"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : llm.py
* Function  : LLM 供应商工厂 — 根据配置创建 LangChain BaseChatModel 实例
"""
from typing import Optional

from langchain_core.language_models import BaseChatModel

from mochi_assistant.config import MochiConfig
from mochi_assistant.logging_config import get_logger

logger = get_logger(__name__)

# 供应商 → (LangChain 类路径, 默认模型)
# 仅内置 DeepSeek / DashScope / OpenAI；其他供应商请使用 OpenAI 兼容模式
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "openai": ("langchain_openai.ChatOpenAI", "gpt-4o"),
    "deepseek": ("langchain_openai.ChatOpenAI", "deepseek-chat"),
    "dashscope": ("langchain_openai.ChatOpenAI", "qwen-turbo"),
}


def _import_class(dotted_path: str):
    """动态导入类，如 'langchain_openai.ChatOpenAI'"""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_llm(config: MochiConfig) -> BaseChatModel:
    """根据 MochiConfig 创建 LLM 实例

    Args:
        config: Mochi 配置对象

    Returns:
        LangChain BaseChatModel 实例

    Raises:
        ValueError: 不支持的供应商
        ImportError: 缺少供应商对应的 LangChain 包
    """
    provider = config.provider.lower()

    if provider not in _PROVIDER_MAP:
        raise ValueError(
            f"不支持的 LLM 供应商: '{provider}'. "
            f"支持的供应商: {', '.join(_PROVIDER_MAP.keys())}"
        )

    class_path, default_model = _PROVIDER_MAP[provider]
    model = config.model or default_model
    logger.info(f"正在初始化 LLM: provider={provider}, model={model}")

    try:
        llm_class = _import_class(class_path)
    except ImportError:
        raise ImportError(
            f"缺少 {provider} 的 LangChain 包。请安装: "
            f"pip install langchain-{provider}"
        )

    # 构建通用参数
    kwargs = {
        "model": model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    # API key
    if config.api_key:
        kwargs["api_key"] = config.api_key

    # base_url（自定义 API 地址）
    if config.base_url:
        kwargs["base_url"] = config.base_url

    llm = llm_class(**kwargs)
    logger.info(f"LLM 初始化成功: {provider}/{model}")
    return llm
