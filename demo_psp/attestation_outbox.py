"""
存证出箱模块

DemoPSP 本地保存支付原始记录，异步提交完整存证副本到 DemoTrustService。

存证链涵盖支付域的核心事件：
  - act:payment:transaction-completed  支付完成
  - demo:payment:proof-verified        支付凭证验证

每份存证记录必须包含完整的上下文字段（delegation_id、trade_no、
participants 等），供信任服务构建跨域可追踪的存证链。
"""

from __future__ import annotations

import json
import uuid
import os

from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest, sign_json
from .database import get_db
from .payment_processor import get_signing_key

TRUST_SERVICE_URL = os.getenv("TRUST_SERVICE_URL", "http://127.0.0.1:8003")

# 存证类型常量
ATTEST_PAYMENT_COMPLETED = "act:payment:transaction-completed"
ATTEST_PROOF_VERIFIED = "demo:payment:proof-verified"


async def enqueue_attestation(
    event_type: str,
    payload: dict,
    delegation_id: str = "",
    task_id: str = "",
    trade_no: str = "",
    out_trade_no: str = "",
    participants: list[str] | None = None,
) -> str:
    """
    存入证出箱（本地持久化），后续异步提交到信任服务。

    参数:
        event_type: 存证事件类型
        payload: 事件载荷（用于哈希计算）
        delegation_id: 关联的委托 ID
        task_id: 关联的 A2A Task ID
        trade_no: 关联的 PSP 交易号
        out_trade_no: 关联的商户订单号
        participants: 参与方列表 [buyer_id, seller_id, psp_id, ...]
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
            "out_trade_no": out_trade_no,
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
            success = await _submit_to_trust(data)
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


async def _submit_to_trust(event: dict) -> bool:
    """
    提交存证到信任服务。

    发送完整的 AttestationRequest，包含 delegation_id、task_id、trade_no、
    participants 等链路关联字段，供信任服务构建可追踪的存证链。
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
            "out_trade_no": payload_data.get("out_trade_no", ""),
            "participants": payload_data.get("participants", []),
            "payload_hash": event["payload_hash"],
            "hash_algorithm": "SHA-256",
            "event_body_or_digest": payload_data,
            "signer_id": "psp",
            "signature_algorithm": "Ed25519",
        }
        # 签发真实 Ed25519 签名，替代 placeholder
        psk = get_signing_key()
        if psk:
            attestation_req["signature"] = sign_json(psk, {
                k: v for k, v in attestation_req.items() if k != "signature"
            })
        else:
            attestation_req["signature"] = "unsigned"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{TRUST_SERVICE_URL}/v1/attestations",
                json=attestation_req,
            )
            return resp.status_code == 200
    except Exception:
        return False
