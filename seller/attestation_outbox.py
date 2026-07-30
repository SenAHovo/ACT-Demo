"""
存证出箱模块

卖方智能体本地保存履约原始记录，异步提交完整存证副本到信任服务（端口 8003）。

存证链涵盖 ACT 四大域的完整事件：
  - act:delegation:created      委托授权创建
  - act:commerce:task-created   商业交互: A2A Task 创建
  - act:commerce:message-sent   商业交互: A2A Message 发送
  - act:payment:completed       支付结算: 支付完成
  - act:commerce:fulfillment-completed  商业交互: 履约完成
"""

from __future__ import annotations

import json
import uuid
import os

from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest
from .database import get_db

TRUST_SERVICE_URL = os.getenv("TRUST_SERVICE_URL", "http://127.0.0.1:8003")

# 存证类型常量
ATTEST_DELEGATION_CREATED = "act:delegation:created"
ATTEST_TASK_CREATED = "act:commerce:task-created"
ATTEST_MESSAGE_SENT = "act:commerce:message-sent"
ATTEST_PAYMENT_COMPLETED = "act:payment:completed"
ATTEST_FULFILLMENT_COMPLETED = "act:commerce:fulfillment-completed"


async def enqueue_attestation(
    event_type: str,
    payload: dict,
    delegation_id: str = "",
    task_id: str = "",
    trade_no: str = "",
    participants: list[str] | None = None,
) -> str:
    """
    存入证出箱（本地持久化），后续异步提交到信任服务。

    参数:
        event_type: 存证事件类型
        payload: 事件载荷（用于哈希计算）
        delegation_id: 关联的委托 ID
        task_id: 关联的 A2A Task ID
        trade_no: 关联的交易号
        participants: 参与方列表 [buyer_id, seller_id, ...]
    """
    db = await get_db()
    try:
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        payload_hash = compute_sha256_digest(payload)
        payload_json = json.dumps({
            "event_type": event_type,
            "event_time": to_iso(utc_now()),
            "delegation_id": delegation_id,
            "task_id": task_id,
            "trade_no": trade_no,
            "participants": participants or [],
            "payload_hash": payload_hash,
        }, ensure_ascii=False)

        await db.execute(
            """INSERT INTO attestation_outbox
               (event_id, event_type, payload_hash, payload_json, submission_status)
               VALUES (?, ?, ?, ?, 'PENDING')""",
            (event_id, event_type, payload_hash, payload_json),
        )
        await db.commit()
        return event_id
    finally:
        await db.close()


async def flush_outbox() -> list[dict]:
    """
    批量提交存证出箱中的待发送记录到信任服务。

    返回: [{"event_id": ..., "success": bool}, ...]
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM attestation_outbox WHERE submission_status = 'PENDING'"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            success = await _submit(data)
            new_status = "SUBMITTED" if success else "RETRYING"
            await db.execute(
                "UPDATE attestation_outbox SET submission_status = ?, retry_count = retry_count + 1 WHERE event_id = ?",
                (new_status, row["event_id"]),
            )
            results.append({"event_id": row["event_id"], "success": success})
        await db.commit()
        return results
    finally:
        await db.close()


async def _submit(event: dict) -> bool:
    """
    提交存证到信任服务。

    发送完整的 AttestationRequest，包含 delegation_id、task_id、trade_no 等
    链路关联字段，供信任服务构建可追踪的存证链。
    """
    try:
        import httpx

        payload_data = {}
        if event.get("payload_json"):
            try:
                payload_data = json.loads(event["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload_data = {}

        attestation_req = {
            "attestation_id": event["event_id"],
            "event_type": event["event_type"],
            "event_time": payload_data.get("event_time", to_iso(utc_now())),
            "delegation_id": payload_data.get("delegation_id", ""),
            "task_id": payload_data.get("task_id", ""),
            "trade_no": payload_data.get("trade_no", ""),
            "participants": payload_data.get("participants", []),
            "payload_hash": event["payload_hash"],
            "hash_algorithm": "SHA-256",
            "event_body_or_digest": payload_data,
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{TRUST_SERVICE_URL}/v1/attestations",
                json=attestation_req,
            )
            return resp.status_code == 200
    except Exception:
        return False
