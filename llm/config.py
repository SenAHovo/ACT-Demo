"""
LLM 配置管理模块

读取环境变量，管理全局和角色级 DeepSeek 配置。
优先级: 角色级配置 → 全局 DeepSeek 配置 → 启动失败
"""

import os
from dataclasses import dataclass, field

# 须先加载 .env
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class LLMConfig:
    """单个 LLM 角色的配置。"""
    base_url: str
    api_key: str
    model: str


def _resolve_config(
    role_prefix: str,
    global_base_url: str,
    global_api_key: str,
    global_model: str,
) -> LLMConfig:
    """按优先级解析配置：角色级 > 全局。"""
    base_url = os.getenv(f"{role_prefix}_LLM_BASE_URL") or global_base_url
    api_key = os.getenv(f"{role_prefix}_LLM_API_KEY") or global_api_key
    model = os.getenv(f"{role_prefix}_LLM_MODEL") or global_model
    return LLMConfig(base_url=base_url, api_key=api_key, model=model)


def load_llm_config() -> dict[str, LLMConfig]:
    """
    加载全局和角色级 LLM 配置。

    Returns:
        {
            "global":    全局配置,
            "buyer":     买方角色级覆盖,
            "seller":    卖方角色级覆盖,
        }
    """
    global_base_url = os.getenv("DEEPSEEK_BASE_URL", "")
    global_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    global_model = os.getenv("DEEPSEEK_MODEL", "")

    # 必填校验
    missing = []
    if not global_base_url:
        missing.append("DEEPSEEK_BASE_URL")
    if not global_api_key:
        missing.append("DEEPSEEK_API_KEY")
    if not global_model:
        missing.append("DEEPSEEK_MODEL")
    if missing:
        raise RuntimeError(
            f"缺少必要的 DeepSeek 环境变量: {', '.join(missing)}。"
            f"请检查 .env 文件。"
        )

    global_config = LLMConfig(
        base_url=global_base_url.strip("/"),
        api_key=global_api_key,
        model=global_model,
    )

    buyer_config = _resolve_config(
        "BUYER", global_base_url.strip("/"), global_api_key, global_model
    )
    seller_config = _resolve_config(
        "SELLER", global_base_url.strip("/"), global_api_key, global_model
    )

    return {
        "global": global_config,
        "buyer": buyer_config,
        "seller": seller_config,
    }


# 项目级默认配置，延迟加载
_config_cache: dict[str, LLMConfig] | None = None


def get_llm_config(role: str = "global") -> LLMConfig:
    """
    获取指定角色的 LLM 配置。首次调用时从环境变量加载并缓存。

    Args:
        role: "global" | "buyer" | "seller"
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = load_llm_config()
    if role not in _config_cache:
        raise ValueError(f"未知角色: {role}，可选: global, buyer, seller")
    return _config_cache[role]
