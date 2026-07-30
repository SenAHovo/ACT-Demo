"""
绑定验证器模块

验证 user_agent_binding_id 和 payment_binding_id。
"""

from __future__ import annotations

import os
import httpx

from shared.errors import ErrorCode, AppError

DELEGATION_SERVICE_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")


async def verify_user_agent_binding(
    user_agent_binding_id: str,
    expected_agent_id: str,
) -> dict:
    """验证委托人-智能体绑定有效且匹配。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{DELEGATION_SERVICE_URL}/v1/user-agent-bindings/{user_agent_binding_id}"
            )
            if resp.status_code != 200:
                raise AppError(ErrorCode.USER_AGENT_BINDING_INVALID, "绑定不存在")

            binding = resp.json()
            if binding.get("status") != "ACTIVE":
                raise AppError(ErrorCode.USER_AGENT_BINDING_INVALID, f"状态: {binding.get('status')}")

            if binding.get("buyer_agent_id") != expected_agent_id:
                raise AppError(ErrorCode.USER_AGENT_BINDING_INVALID, "agent_id 不匹配")

            return binding
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.USER_AGENT_BINDING_INVALID, str(e))


async def verify_payment_binding(
    payment_binding_id: str,
    expected_agent_id: str,
    expected_sub_account_id: str,
) -> dict:
    """验证支付绑定有效且匹配。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{DELEGATION_SERVICE_URL}/v1/payment-bindings/{payment_binding_id}"
            )
            if resp.status_code != 200:
                raise AppError(ErrorCode.PAYMENT_BINDING_INVALID, "支付绑定不存在")

            binding = resp.json()
            if binding.get("status") != "ACTIVE":
                raise AppError(ErrorCode.PAYMENT_BINDING_INVALID, f"状态: {binding.get('status')}")

            if binding.get("buyer_agent_id") != expected_agent_id:
                raise AppError(ErrorCode.PAYMENT_BINDING_INVALID, "agent_id 不匹配")

            if binding.get("sub_account_id") != expected_sub_account_id:
                raise AppError(ErrorCode.PAYMENT_BINDING_INVALID, "sub_account_id 不匹配")

            return binding
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.PAYMENT_BINDING_INVALID, str(e))
