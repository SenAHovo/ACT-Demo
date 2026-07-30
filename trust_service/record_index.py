"""
记录索引模块

保存签名事件副本或摘要，维护原始记录定位引用。
"""

import json, uuid
from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError
from .database import get_db
from .event_registry import is_valid_event_type


async def store_attestation(attestation: dict) -> dict:
    """存储存证记录并返回 attestation_id。"""
    if not is_valid_event_type(attestation.get("event_type", "")):
        raise AppError(ErrorCode.INVALID_EVENT_TYPE, f"非法事件类型: {attestation.get('event_type')}")

    attestation_id = attestation.get("attestation_id") or f"att_{uuid.uuid4().hex[:16]}"
    now_iso = to_iso(utc_now())

    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO attestation_records
               (attestation_id, event_type, event_time, record_created_at,
                intent_id, delegation_id, session_id, task_id,
                out_trade_no, trade_no, upstream_links, participants,
                payload_hash, hash_algorithm, event_body, signer_id,
                signature, source_record_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attestation_id,
                attestation.get("event_type", ""),
                attestation.get("event_time", now_iso),
                now_iso,
                attestation.get("intent_id"),
                attestation.get("delegation_id"),
                attestation.get("session_id"),
                attestation.get("task_id"),
                attestation.get("out_trade_no"),
                attestation.get("trade_no"),
                json.dumps(attestation.get("upstream_attestation_ids", [])),
                json.dumps(attestation.get("participants", [])),
                attestation.get("payload_hash", ""),
                attestation.get("hash_algorithm", "SHA-256"),
                json.dumps(attestation.get("event_body_or_digest", {})),
                attestation.get("signer_id", ""),
                attestation.get("signature", ""),
                attestation.get("source_record_ref"),
            ),
        )
        await db.commit()
        return {"attestation_id": attestation_id, "status": "STORED"}
    finally:
        await db.close()


async def get_attestation(attestation_id: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM attestation_records WHERE attestation_id = ?", (attestation_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.ATTESTATION_NOT_FOUND, f"存证未找到: {attestation_id}")
        return dict(row)
    finally:
        await db.close()


async def list_attestations(
    delegation_id: str = "",
    out_trade_no: str = "",
    event_type: str = "",
    limit: int = 100,
) -> list[dict]:
    db = await get_db()
    try:
        conditions = []
        params: list = []
        if delegation_id:
            conditions.append("delegation_id = ?")
            params.append(delegation_id)
        if out_trade_no:
            conditions.append("out_trade_no = ?")
            params.append(out_trade_no)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = await db.execute(
            f"SELECT * FROM attestation_records WHERE {where} ORDER BY record_created_at LIMIT ?",
            params + [limit],
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
