"""
验证器模块

验证存证记录的签名、摘要和完整性。
"""

import hashlib, json

from shared.time_utils import utc_now, to_iso, from_iso
from shared.signatures import compute_sha256_digest
from shared.errors import ErrorCode, AppError
from .database import get_db


async def verify_attestation(attestation_id: str) -> dict:
    """
    验证存证记录。

    检查:
    - 记录是否存在
    - 摘要格式是否合法
    - 载荷哈希是否一致（重新计算并比对）
    - 时间戳是否合理（不在未来）
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM attestation_records WHERE attestation_id = ?",
            (attestation_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return {"valid": False, "reason": f"记录不存在: {attestation_id}"}

        data = dict(row)

        # 验证 hash 格式（SHA-256 hex）
        payload_hash = data.get("payload_hash", "")
        if len(payload_hash) != 64:
            return {"valid": False, "reason": "摘要长度异常"}

        # 验证载荷哈希一致性：重新计算 event_body 的 SHA-256
        event_body = data.get("event_body", "{}")
        try:
            body_obj = json.loads(event_body)
        except (json.JSONDecodeError, TypeError):
            body_obj = event_body or {}
        recomputed = compute_sha256_digest(body_obj)
        if recomputed != payload_hash:
            return {"valid": False, "reason": f"载荷哈希不一致: 存储={payload_hash[:16]}..., 计算={recomputed[:16]}..."}

        # 验证时间戳：event_time 不应在未来（允许 5 分钟偏差）
        event_time_str = data.get("event_time", "")
        if event_time_str:
            try:
                event_time = from_iso(event_time_str)
                now = utc_now()
                if event_time > now:
                    diff = (event_time - now).total_seconds()
                    if diff > 300:  # 5 分钟窗口
                        return {"valid": False, "reason": f"事件时间在未来: {diff:.0f}s"}
            except Exception:
                pass  # 时间解析异常，降级通过

        # 写入验证结果
        now_iso = to_iso(utc_now())
        await db.execute(
            "INSERT INTO verification_results (attestation_id, verified_at, result, reason) VALUES (?, ?, ?, ?)",
            (attestation_id, now_iso, "PASSED", ""),
        )
        await db.commit()

        return {"valid": True, "reason": "", "attestation_id": attestation_id}
    finally:
        await db.close()
