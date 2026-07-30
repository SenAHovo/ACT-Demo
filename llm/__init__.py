"""
llm/ — DeepSeek API 适配层

为买方和卖方智能体提供统一的 LLM 调用接口，
支持全局配置和角色级覆盖。
"""

from .config import get_llm_config, load_llm_config, LLMConfig
from .deepseek_adapter import DeepSeekAdapter
from .client import LLMClient

__all__ = [
    "get_llm_config",
    "load_llm_config",
    "LLMConfig",
    "DeepSeekAdapter",
    "LLMClient",
]
