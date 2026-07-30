"""
DeepSeek API 适配器

基于 OpenAI SDK 调用 DeepSeek API（兼容 OpenAI 格式）。
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from .config import LLMConfig


class DeepSeekAdapter:
    """DeepSeek API 适配器，封装 OpenAI SDK 调用。"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    @property
    def model(self) -> str:
        return self.config.model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """
        调用 DeepSeek chat completion，返回模型文本响应。

        Args:
            messages: OpenAI 格式的消息列表
            temperature: 采样温度
            max_tokens: 最大输出 tokens
            response_format: 可选，如 {"type": "json_object"}

        Returns:
            模型响应文本

        Raises:
            RuntimeError: API 调用失败
        """
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError("DeepSeek 返回空响应")
            return content
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 调用失败: {e}") from e

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """
        调用 DeepSeek chat completion 并支持 Function Calling + 思考模式。

        Returns:
            {
                "role": "assistant",
                "content": str | None,
                "reasoning_content": str | None,  # 思维链内容（思考模式）
                "tool_calls": list[dict] | None,
                "finish_reason": str,
            }
        """
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
            "tool_choice": tool_choice,
            "extra_body": {"thinking": {"type": "enabled"}},
        }

        try:
            response = self._client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            result: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content,
                "reasoning_content": getattr(msg, 'reasoning_content', None),
                "finish_reason": response.choices[0].finish_reason,
                "tool_calls": None,
            }
            if msg.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            return result
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 调用失败: {e}") from e

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        调用 DeepSeek 并要求 JSON 格式输出，返回解析后的 dict。

        Raises:
            RuntimeError: API 调用失败或 JSON 解析失败
        """
        raw = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"DeepSeek 返回的不是有效 JSON: {e}") from e

    def chat_with_tools_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        """
        流式调用 DeepSeek chat completion（支持 Function Calling + 思考模式）。

        思考模式下（thinking: enabled），模型会先输出思维链（reasoning_content），
        再输出最终回答（content），两者在流中被分开返回。
        标准模型（如 deepseek-v4-flash）也支持思考模式。

        Yields:
            dict: {"type": "reasoning", "text": str} — 思维链增量（思考模式下）
            dict: {"type": "content", "text": str} — 输出文本增量
            dict: {"type": "tool_calls", "tool_calls": list} — 完整的 tool_calls（流结束后）
            dict: {"type": "done"} — 流结束
        """
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": tools,
            "stream": True,
            "extra_body": {"thinking": {"type": "enabled"}},
        }

        try:
            stream = self._client.chat.completions.create(**kwargs)
            accumulated_tool_calls: list[dict] = []

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # 思维链内容（思考模式下的 reasoning_content）
                reasoning = getattr(delta, 'reasoning_content', None)
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}

                # 输出文本内容
                if delta.content:
                    yield {"type": "content", "text": delta.content}

                # 工具调用（增量累积）
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        while len(accumulated_tool_calls) <= idx:
                            accumulated_tool_calls.append({
                                "id": "", "function": {"name": "", "arguments": ""}
                            })
                        if tc_delta.id:
                            accumulated_tool_calls[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                accumulated_tool_calls[idx]["function"]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                accumulated_tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments

            # 流结束
            if accumulated_tool_calls:
                yield {
                    "type": "tool_calls",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "function": tc["function"],
                        }
                        for tc in accumulated_tool_calls
                    ],
                }

            yield {"type": "done"}

        except Exception as e:
            raise RuntimeError(f"DeepSeek API 流式调用失败: {e}") from e
