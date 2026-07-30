"""
存证客户端模块

委托授权服务向 DemoTrustService 异步提交存证事件的客户端。
"""

from __future__ import annotations

import os


TRUST_SERVICE_URL = os.getenv("TRUST_SERVICE_URL", "http://127.0.0.1:8003")


async def submit_attestation(event: dict) -> dict | None:
    """
    向 DemoTrustService 提交存证事件。

    异步提交，失败不抛异常，由调用方记录重试。

    Args:
        event: AttestationRecord 字典

    Returns:
        成功返回响应字典，失败返回 None
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{TRUST_SERVICE_URL}/v1/attestations",
                json=event,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
    except Exception:
        return None
