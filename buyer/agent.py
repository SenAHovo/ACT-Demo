"""
买方智能体 — 主控制器

编排整体执行流程：意图解析 → 发现 → 决策 → 支付 → 履约 → 汇总。
"""

from __future__ import annotations

import asyncio, os, httpx, uuid
from decimal import Decimal

from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest
from shared.interaction import generate_interaction_id
from .database import init_db
from .discovery_client import discover_seller, discover_services
from .authentication_client import authenticate_with_seller
from .payment_client import parse_payment_needed, execute_payment
from .artifact_store import save_artifact
from .task_ledger import record_task, update_task, get_total_spent

DELEGATION_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")
BUYER_ID = "urn:demo:agent:buyer:001"
SELLER_ID = "urn:demo:agent:seller:research-service-001"

SERVICE_ORDER = [
    {"service_id": "doc.weekly.report", "input": {}},
    {"service_id": "lifestyle.travel.guide", "input": {"destination": "杭州", "origin": "北京", "days": 3}},
    {"service_id": "utility.translation", "input": {"text": "智能体交易是人工智能在商业领域的创新应用。", "source_lang": "zh", "target_lang": "en"}},
]


async def run_buyer_agent():
    """买方智能体完整执行流程。"""
    await init_db()
    print("[Buyer] 初始化完成")

    # 1. 发现卖方
    print("[Buyer] 发现卖方智能体...")
    await discover_seller()

    services = await discover_services()
    print(f"[Buyer] 发现 {len(services)} 项服务")

    # 2. 认证
    print("[Buyer] 建立认证会话...")
    session_id = await authenticate_with_seller()

    # 3. 创建意图和授权
    print("[Buyer] 创建委托授权...")
    delegation = await _create_delegation(session_id)

    # 4. 从委托服务获取买方实际凭证 ID
    async with httpx.AsyncClient(timeout=10.0) as client:
        identity_resp = await client.get(f"{DELEGATION_URL}/v1/identities/{BUYER_ID}")
        buyer_identity = identity_resp.json()
        credential_id = buyer_identity["credential_id"]
        print(f"[Buyer] 凭证 ID: {credential_id}")

    # 5. 流水线执行三项服务
    results = []
    prev_artifact = None

    for svc in SERVICE_ORDER:
        task_id = generate_interaction_id("task")
        print(f"\n[Buyer] ===== 购买 {svc['service_id']} =====")

        # 构造输入（后续服务引用上游 Artifact）
        input_data = dict(svc["input"])
        if prev_artifact:
            input_data["source_artifact"] = prev_artifact
            input_data["source_artifact_id"] = prev_artifact.get("artifact_id")

        result = await _purchase_service(
            session_id, task_id, svc["service_id"],
            input_data, delegation, credential_id,
        )

        if result.get("status") == "FULFILLED":
            artifact = result.get("artifact", {})
            await save_artifact(artifact, svc["service_id"], result.get("trade_no", ""))
            prev_artifact = artifact
            results.append({"service": svc["service_id"], "status": "OK", "artifact_id": artifact.get("artifact_id")})
        else:
            results.append({"service": svc["service_id"], "status": "FAILED", "reason": result.get("reason", "未知")})
            break

    # 5. 汇总
    total = await get_total_spent(delegation["delegation_id"], session_id)
    print(f"\n[Buyer] ===== 任务完成 =====")
    print(f"[Buyer] 总支出: {total} CNY")
    for r in results:
        status_str = "OK" if r["status"] == "OK" else f"FAILED ({r.get('reason', '未知')})"
        print(f"  {r['service']}: {status_str}")

    return {"results": results, "total_spent": str(total), "delegation_id": delegation["delegation_id"]}


async def _create_delegation(session_id: str) -> dict:
    """创建 ISR → 签发 IAC。"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 创建 ISR
        intent_resp = await client.post(f"{DELEGATION_URL}/v1/intents", json={
            "task_goal": "生成周报、查询旅游攻略、翻译文档",
            "agent_id": BUYER_ID,
            "user_agent_binding_id": "uab_demo_001",
            "max_total_amount": "1.00",
            "max_single_amount": "0.50",
            "allowed_sellers": [SELLER_ID],
            "allowed_categories": ["document.office", "lifestyle.travel", "utility"],
            "allowed_payment_methods": ["urn:demo:payment:local-balance:v1"],
        })
        intent = intent_resp.json()

        # 签发 IAC
        del_resp = await client.post(f"{DELEGATION_URL}/v1/delegations", json={
            "intent_id": intent["intent_id"],
        })
        delegation = del_resp.json()
        print(f"[Buyer] IAC 签发: {delegation['delegation_id']}")
        return delegation


async def _purchase_service(
    session_id: str, task_id: str, service_id: str,
    input_data: dict, delegation: dict, credential_id: str,
) -> dict:
    """单次购买流程：调用 → 支付 → 重试。"""
    message_id = generate_interaction_id("msg")

    envelope = {
        "session_id": session_id,
        "task_id": task_id,
        "message_id": message_id,
        "sender_role": "buyer_agent",
        "sender_id": BUYER_ID,
        "receiver_id": SELLER_ID,
        "message_type": "service_invocation",
        "task_state": "SUBMITTED",
        "state_changed_at": to_iso(utc_now()),
        "data_items": [{"content_type": "application/json", "payload": input_data}],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 第一次调用：可能返回 402
        resp = await client.post(
            f"http://127.0.0.1:8001/v1/services/{service_id}/invoke",
            json={"envelope": envelope, "invocation": {"service_id": service_id, "input": input_data, "delegation_id": delegation["delegation_id"]}},
        )

        if resp.status_code == 402:
            payment_needed = parse_payment_needed(resp.json(), resp.headers)

            # 记录待支付任务
            await record_task(task_id, session_id, service_id, delegation["delegation_id"], payment_needed["amount"])

            # 支付（返回完整 PSP 结果，含 proof）
            payment_result = await execute_payment(
                payment_needed, delegation, session_id, task_id, credential_id,
            )

            if not payment_result:
                await update_task(task_id, "", payment_needed["amount"], "FAILED")
                return {"status": "FAILED", "reason": "支付失败"}

            trade_no = payment_result.get("trade_no", "")
            proof = payment_result.get("proof", {})

            # 带 PSP 签发的完整支付凭证重试
            message_id2 = generate_interaction_id("msg")
            envelope2 = {**envelope, "message_id": message_id2, "state_changed_at": to_iso(utc_now())}

            resp2 = await client.post(
                f"http://127.0.0.1:8001/v1/services/{service_id}/invoke",
                json={
                    "envelope": envelope2,
                    "invocation": {
                        "service_id": service_id,
                        "input": input_data,
                        "delegation_id": delegation["delegation_id"],
                        "payment_proof": proof,
                    },
                },
            )

            if resp2.status_code == 200:
                data = resp2.json()
                data["trade_no"] = trade_no
                await update_task(task_id, trade_no, payment_needed["amount"], "COMPLETED")
                return data
            else:
                print(f"[Buyer] 重试失败: HTTP {resp2.status_code}, body={resp2.text[:200]}")
                return {"status": "FAILED", "reason": f"重试失败: HTTP {resp2.status_code}"}

        elif resp.status_code == 200:
            return resp.json()
        else:
            return {"status": "FAILED", "reason": f"HTTP {resp.status_code}"}
