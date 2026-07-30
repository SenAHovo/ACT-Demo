"""
买家 A2A 客户端 — 通过案例内部任务协议与卖家智能体交互（非 Google A2A 标准实现）

商业交互域的核心实现：
  1. 通过 Agent Card 发现卖家
  2. 在卖家上创建任务
  3. 通过任务消息协商服务
  4. 处理 HTTP 402 支付流程
  5. 获取 Artifact 并下载文件
"""

from __future__ import annotations

import asyncio
import os
import json

import httpx

SELLER_URL = os.getenv("SELLER_AGENT_URL", "http://127.0.0.1:8001")
PSP_URL = os.getenv("DEMO_PSP_URL", "http://127.0.0.1:8002")
BUYER_ID = "urn:demo:agent:buyer:001"


async def discover_seller() -> dict:
    """A2A 发现: 获取卖家 Agent Card。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SELLER_URL}/.well-known/agent-card.json")
        resp.raise_for_status()
        return resp.json()


async def discover_services() -> list[dict]:
    """获取卖家服务目录（从 Agent Card 解析 skills）。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SELLER_URL}/v1/catalog")
        resp.raise_for_status()
        return resp.json()


async def create_a2a_task(
    goal: str,
    delegation_id: str = "",
    buyer_agent_id: str = BUYER_ID,
) -> dict:
    """在卖家智能体上创建 A2A Task。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks",
            json={
                "buyer_agent_id": buyer_agent_id,
                "goal": goal,
                "delegation_id": delegation_id,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def send_task_message(
    task_id: str,
    content: str,
    sender_role: str = "buyer_agent",
) -> dict:
    """向 Task 发送消息，卖家智能体解析并处理。"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks/{task_id}/messages",
            json={
                "sender_role": sender_role,
                "content": content,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_task(task_id: str) -> dict:
    """查询 A2A Task 状态。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SELLER_URL}/v1/a2a/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()


async def get_task_artifacts(task_id: str) -> list[dict]:
    """获取 Task 的产出物列表。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SELLER_URL}/v1/a2a/tasks/{task_id}/artifacts")
        resp.raise_for_status()
        return resp.json()


async def execute_payment_after_delegation(
    payment_needed: dict,
    delegation: dict,
    session_id: str,
    task_id: str,
    credential_id: str,
) -> dict | None:
    """
    执行 PSP 支付。

    Returns:
        完整 PSP 响应 dict（含 trade_no、proof、new_balance），失败返回 None
    """
    import uuid

    req = {
        "request_id": f"req_{uuid.uuid4().hex[:16]}",
        "delegation_id": delegation["delegation_id"],
        "user_agent_binding_id": delegation.get("user_agent_binding_id", "uab_demo_001"),
        "payment_binding_id": "paybind_buyer_001",
        "agent_credential_ref": credential_id,
        "sub_account_id": "subacct_buyer_001",
        "out_trade_no": payment_needed["out_trade_no"],
        "resource_id": payment_needed["resource_id"],
        "resource_digest": payment_needed.get("resource_digest", ""),
        "service_id": payment_needed["service_id"],
        "service_category": payment_needed.get("service_category", ""),
        "seller_id": payment_needed.get("seller_unique_id", "urn:demo:agent:seller:research-service-001"),
        "buyer_agent_id": BUYER_ID,
        "amount": payment_needed["amount"],
        "currency": payment_needed.get("currency", "CNY"),
        "method_id": payment_needed["method_id"],
        "session_id": session_id,
        "task_id": task_id,
        "signature": "placeholder",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{PSP_URL}/v1/payments", json=req)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[A2A Payment] 支付成功: {payment_needed['amount']} CNY, trade_no={data.get('trade_no', '')}")
            return data  # 返回完整结果：trade_no, proof, new_balance
        else:
            print(f"[A2A Payment] 支付失败: {resp.status_code} {resp.text}")
            return None


async def pay_and_fulfill_task(
    task_id: str,
    service_id: str,
    skill_id: str,
    input_data: dict,
    payment_needed: dict,
    delegation: dict,
    session_id: str,
    credential_id: str,
) -> dict:
    """
    完整的支付 + 履约流程：
    1. 执行 PSP 支付（获取完整支付凭证）
    2. 将 PSP 签发的支付凭证（proof）完整传递给卖方
    3. 卖方独立验证 proof 中的金额、卖方 ID、买方 ID 匹配后交付服务
    4. 返回履约结果
    """
    # 执行支付，获取完整结果（含 proof）
    payment_result = await execute_payment_after_delegation(
        payment_needed, delegation, session_id, task_id, credential_id
    )
    if not payment_result:
        return {"status": "FAILED", "error": "支付失败"}

    trade_no = payment_result.get("trade_no", "")
    proof = payment_result.get("proof", {})

    # 通知卖家支付完成，传递 PSP 签发的完整支付凭证
    # 卖方凭此 proof 向 PSP 独立验证交易的金额、买卖方身份是否匹配
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks/{task_id}/pay",
            json={
                "service_id": service_id,
                "skill_id": skill_id,
                "input_data": input_data,
                "payment_proof": proof,
                "trade_no": trade_no,
            },
        )
        resp.raise_for_status()
        return resp.json()
