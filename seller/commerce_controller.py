"""
商业控制器模块

服务调用、HTTP 402 支付要求、凭证验证、Skill 激活。
"""

from __future__ import annotations

import uuid
import json

from decimal import Decimal
from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest
from shared.errors import ErrorCode, AppError
from .database import get_db
from .catalog import get_service
from .skill_registry import execute_skill
from .payment_adapter import verify_payment_proof


async def handle_service_invocation(invocation: dict, envelope: dict) -> dict:
    """
    处理服务调用请求。

    流程:
    1. 查服务目录
    2. 记录调用
    3. 检查是否携带支付凭证
    4. 无凭证 → 生成订单并返回 HTTP 402(Payment-Needed)
    5. 有凭证 → 验证 → 执行 Skill → 返回 Artifact
    """
    service_id = invocation.get("service_id")
    svc = await get_service(service_id)

    session_id = envelope.get("session_id", "")
    task_id = envelope.get("task_id", "")
    message_id = envelope.get("message_id", "")
    buyer_agent_id = envelope.get("sender_id", "")
    input_data = invocation.get("input", {})
    input_digest = compute_sha256_digest(input_data)
    delegation_id = invocation.get("delegation_id", "")

    # 记录调用
    invoke_id = f"invoke_{uuid.uuid4().hex[:16]}"
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO service_invocations
               (invoke_id, session_id, task_id, message_id, service_id,
                input_digest, delegation_id, buyer_agent_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (invoke_id, session_id, task_id, message_id, service_id,
             input_digest, delegation_id, buyer_agent_id, to_iso(utc_now())),
        )
        await db.commit()
    finally:
        await db.close()

    # 检查支付头
    payment_proof = _extract_payment_proof_header(invocation)

    if payment_proof:
        # 已支付 → 验证凭证 → 执行 Skill
        await verify_payment_proof(payment_proof, expected_amount=svc["price"])
        return await _execute_service(invoke_id, svc, input_data, session_id, task_id)
    else:
        # 未支付 → 生成订单 → 返回 Payment-Needed
        return await _create_payment_needed(invoke_id, svc, session_id, task_id)


def _extract_payment_proof_header(invocation: dict) -> dict | None:
    """从调用中提取支付凭证（简化版：检查 proof 字段）。"""
    return invocation.get("payment_proof") or invocation.get("proof")


async def _create_payment_needed(
    invoke_id: str, svc: dict, session_id: str, task_id: str
) -> dict:
    """生成订单并构造 HTTP 402 Payment-Needed 响应。"""
    out_trade_no = f"order_{uuid.uuid4().hex[:16]}"
    resource_id = f"svc_{svc['service_id']}_{uuid.uuid4().hex[:8]}"

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO seller_orders
               (out_trade_no, task_id, service_id, resource_id, resource_digest,
                amount, currency, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'WAIT_BUYER_PAY', ?)""",
            (out_trade_no, task_id, svc["service_id"], resource_id,
             compute_sha256_digest({"resource_id": resource_id}),
             svc["price"], svc["currency"], to_iso(utc_now())),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "status": "PAYMENT_REQUIRED",
        "payment_needed": {
            "method_id": "urn:demo:payment:local-balance:v1",
            "psp_id": "urn:demo:psp:local:v1",
            "endpoint": "http://127.0.0.1:8002/v1/payments",
            "out_trade_no": out_trade_no,
            "amount": svc["price"],
            "currency": svc["currency"],
            "resource_id": resource_id,
            "resource_digest": compute_sha256_digest({"resource_id": resource_id}),
            "pay_before": to_iso(utc_now()),
            "seller_unique_id": "urn:demo:agent:seller:research-service-001",
            "buyer_unique_id": "placeholder",
            "service_id": svc["service_id"],
            "service_category": svc["category"],
            "session_id": session_id,
            "task_id": task_id,
        },
    }


async def _execute_service(
    invoke_id: str, svc: dict, input_data: dict,
    session_id: str, task_id: str,
) -> dict:
    """验证支付后执行 Skill 并生成 Artifact。"""
    skill_result = await execute_skill(svc["skill_id"], input_data)

    artifact_id = f"artifact_{uuid.uuid4().hex[:16]}"
    payload = skill_result.get("payload", {})
    content_digest = compute_sha256_digest(payload)

    db = await get_db()
    try:
        import datetime
        now = utc_now()
        # 将 datetime 转为 ISO 字符串，避免 aiosqlite 不接受 datetime 对象的问题
        now_iso = to_iso(now)

        await db.execute(
            """INSERT INTO artifacts
               (artifact_id, artifact_type, session_id, task_id,
                service_id, content_digest, payload, source_artifact_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (artifact_id, skill_result.get("artifact_type", "unknown"),
             session_id, task_id, svc["service_id"],
             content_digest, json.dumps(payload),
             json.dumps(skill_result.get("source_artifact_ids", [])),
             now_iso),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "status": "FULFILLED",
        "artifact": {
            "artifact_id": artifact_id,
            "artifact_type": skill_result.get("artifact_type"),
            "content_digest": content_digest,
            "payload": payload,
            "created_at": to_iso(utc_now()),
            "producer_agent_id": "urn:demo:agent:seller:research-service-001",
            "service_id": svc["service_id"],
        },
    }


async def get_order_status(out_trade_no: str) -> dict:
    """查询订单状态。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM seller_orders WHERE out_trade_no = ?", (out_trade_no,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.PAYMENT_NOT_FOUND, f"订单不存在: {out_trade_no}")
        return dict(row)
    finally:
        await db.close()
