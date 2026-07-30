"""
LLM 统一客户端

提供买方和卖方智能体使用的统一 LLM 调用接口。
封装 DeepSeekAdapter，按角色自动选择配置。
"""

from __future__ import annotations

from .config import get_llm_config
from .deepseek_adapter import DeepSeekAdapter


class LLMClient:
    """统一 LLM 客户端。

    用法:
        client = LLMClient("buyer")    # 使用买方配置
        result = client.chat([{"role": "user", "content": "..."}])

        client = LLMClient("seller")   # 使用卖方配置
    """

    def __init__(self, role: str = "buyer"):
        config = get_llm_config(role)
        self._role = role
        self._adapter = DeepSeekAdapter(config)

    @property
    def model(self) -> str:
        return self._adapter.model

    @property
    def role(self) -> str:
        return self._role

    def chat(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        单轮对话：发送 user prompt，返回模型文本响应。

        Args:
            user_prompt: 用户消息
            system_prompt: 可选的系统提示
            temperature: 采样温度
            max_tokens: 最大输出 tokens
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return self._adapter.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def chat_json(
        self,
        user_prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """
        单轮对话，要求 JSON 格式输出。

        Args:
            user_prompt: 用户消息（应包含 JSON 格式要求）
            system_prompt: 可选的系统提示
            temperature: 采样温度
            max_tokens: 最大输出 tokens
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return self._adapter.chat_json(messages, temperature=temperature, max_tokens=max_tokens)

    def chat_with_messages(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """多轮对话：直接传入完整的 messages 列表。"""
        return self._adapter.chat(messages, temperature=temperature, max_tokens=max_tokens)
