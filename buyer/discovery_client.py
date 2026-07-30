"""发现客户端 — 获取卖方 Agent Card 和服务目录。"""
import os, httpx

SELLER_URL = os.getenv("SELLER_AGENT_URL", "http://127.0.0.1:8001")

async def discover_seller() -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{SELLER_URL}/.well-known/agent-card.json")
        resp.raise_for_status()
        return resp.json()

async def discover_services() -> list[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{SELLER_URL}/v1/catalog")
        resp.raise_for_status()
        return resp.json()
