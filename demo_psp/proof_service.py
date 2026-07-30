"""
凭证服务模块

签发 PaymentProof、验证凭证、检查重复使用。
"""

from __future__ import annotations

import json

from shared.signatures import verify_json
from shared.time_utils import utc_now, from_iso, is_expired
from shared.errors import ErrorCode, AppError
from .database import get_db
from .trade_store import get_proof as _get_proof_from_store
from .payment_processor import get_public_key


async def verify_proof(proof_data: dict) -> dict:
    """
    验证支付凭证的有效性。

    检查:
    - 凭证存在
    - Ed25519 签名有效（不可抵赖性的密码学基础）
    - 状态为 SUCCESS
    - 未过期
    - 资源/主体/金额匹配
    """
    trade_no = proof_data.get("trade_no")
    if not trade_no:
        return {"valid": False, "reason": "缺少 trade_no"}

    # 优先从共享内存存储读取（同一进程内 payment_processor 写入，保证可见性）
    stored = _get_proof_from_store(trade_no)

    # 共享存储未命中则回退到数据库查询
    if stored is None:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM payment_proofs WHERE trade_no = ?", (trade_no,)
            )
            row = await cursor.fetchone()
            if row is None:
                return {"valid": False, "reason": f"凭证不存在: {trade_no}"}
            stored = json.loads(row["proof_data"])
        finally:
            await db.close()

    # ---- 验证 Ed25519 签名（不可抵赖性的密码学基础） ----
    psp_public_key = get_public_key()
    if psp_public_key is None:
        return {"valid": False, "reason": "PSP 签名公钥未初始化"}

    # 构造签名前的原始载荷（去除后添加的 signature 字段）
    payload_without_sig = {k: v for k, v in stored.items() if k != "signature"}
    stored_sig = stored.get("signature", "")
    if not stored_sig or stored_sig == "unsigned":
        return {"valid": False, "reason": "凭证缺少有效签名"}
    if not verify_json(psp_public_key, payload_without_sig, stored_sig):
        return {"valid": False, "reason": "凭证 Ed25519 签名验证失败——凭证可能被篡改"}

    # 同时验证提交的 proof_data 与存储记录一致
    submitted_sig = proof_data.get("signature", "")
    if submitted_sig and submitted_sig != stored_sig:
        payload_submitted = {k: v for k, v in proof_data.items() if k != "signature"}
        if not verify_json(psp_public_key, payload_submitted, submitted_sig):
            return {"valid": False, "reason": "提交的凭证签名无效"}

    # 检查状态
    if stored.get("status") != "SUCCESS":
        return {"valid": False, "reason": f"凭证状态: {stored.get('status')}"}

    # 检查过期
    if stored.get("expires_at"):
        if is_expired(from_iso(stored["expires_at"])):
            return {"valid": False, "reason": "凭证已过期"}

    # 检查关键字段匹配
    checks = {
        "resource_id": "资源 ID 不匹配",
        "seller_id": "卖方 ID 不匹配",
        "buyer_agent_id": "买方 ID 不匹配",
        "amount": "金额不匹配",
        "session_id": "会话 ID 不匹配",
        "task_id": "任务 ID 不匹配",
    }
    for field, msg in checks.items():
        pv = proof_data.get(field)
        sv = stored.get(field)
        if pv and sv and str(pv) != str(sv):
            return {"valid": False, "reason": msg}

    return {"valid": True, "reason": "", "stored": stored}


async def get_proof(trade_no: str) -> dict | None:
    """获取支付凭证。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM payment_proofs WHERE trade_no = ?", (trade_no,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["proof_data"])
    finally:
        await db.close()
