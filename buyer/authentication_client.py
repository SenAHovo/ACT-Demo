"""认证客户端 — 与卖方建立本地已鉴别会话。"""
import os, httpx, uuid

SELLER_URL = os.getenv("SELLER_AGENT_URL", "http://127.0.0.1:8001")

async def authenticate_with_seller() -> str:
    session_id = f"session_{uuid.uuid4().hex[:16]}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(f"{SELLER_URL}/v1/sessions/authenticate", json={"assertion_id": session_id})
        resp.raise_for_status()
    return session_id
