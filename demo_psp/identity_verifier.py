"""
身份验证器模块

验证买方智能体的本地凭证及状态。
"""

from __future__ import annotations

import os
import httpx

from shared.errors import ErrorCode, AppError

DELEGATION_SERVICE_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")


async def verify_agent_credential(credential_id: str, expected_agent_id: str = "") -> dict:
    """验证凭证存在、状态为 ACTIVE，且归属匹配。

    Args:
        credential_id: 凭证 ID
        expected_agent_id: 期望的智能体 ID（若提供则校验归属）
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{DELEGATION_SERVICE_URL}/v1/credentials/{credential_id}/status"
            )
            if resp.status_code != 200:
                raise AppError(ErrorCode.INVALID_CREDENTIAL, f"凭证状态查询失败: {resp.status_code}")
            data = resp.json()
            if data.get("status") != "ACTIVE":
                raise AppError(ErrorCode.INVALID_CREDENTIAL, f"凭证状态: {data.get('status')}")

            # 验证凭证归属：credential 必须属于声明它的智能体
            if expected_agent_id and data.get("agent_id") != expected_agent_id:
                raise AppError(
                    ErrorCode.INVALID_CREDENTIAL,
                    f"凭证 agent_id 不匹配: {data.get('agent_id')} != {expected_agent_id}",
                )
            return data
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.IDENTITY_NOT_FOUND, f"无法连接身份服务: {e}")
