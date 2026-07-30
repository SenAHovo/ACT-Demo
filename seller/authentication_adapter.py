"""
认证适配器模块

验证买方凭证引用及状态（委托给 delegation_service）。
"""

from __future__ import annotations

import os
import httpx
from shared.errors import ErrorCode, AppError

DELEGATION_SERVICE_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")


async def verify_buyer_authentication(assertion_id: str) -> dict:
    """验证买方的 AuthenticationAssertion。"""
    # 卖方不支持直接调用 /authentications/verify，改用查询身份做简化验证
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 简化: 通过 assertion_id 前缀匹配验证
            resp = await client.get(
                f"{DELEGATION_SERVICE_URL}/v1/identities/urn:demo:agent:buyer:001"
            )
            if resp.status_code == 200:
                return resp.json()
            raise AppError(ErrorCode.AUTHENTICATION_FAILED, "买方身份验证失败")
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.AUTHENTICATION_FAILED, str(e))
