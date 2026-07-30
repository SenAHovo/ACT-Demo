"""
支付绑定模块

建立买方智能体与模拟支付方法、模拟子账户的绑定关系。
"""

from __future__ import annotations

from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError
from .database import get_db


async def create_payment_binding(
    payment_binding_id: str,
    user_agent_binding_id: str,
    buyer_agent_id: str,
    payment_method_id: str,
    sub_account_id: str,
    valid_until: str | None = None,
) -> dict:
    """创建支付绑定。"""
    db = await get_db()
    try:
        now_iso = to_iso(utc_now())
        await db.execute(
            """INSERT OR IGNORE INTO payment_bindings
               (payment_binding_id, user_agent_binding_id, buyer_agent_id,
                payment_method_id, sub_account_id, status, valid_from, valid_until)
               VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
            (payment_binding_id, user_agent_binding_id, buyer_agent_id,
             payment_method_id, sub_account_id, now_iso, valid_until),
        )
        await db.commit()
        return await _get_binding(db, payment_binding_id)
    finally:
        await db.close()


async def get_payment_binding(payment_binding_id: str) -> dict:
    """获取支付绑定。"""
    db = await get_db()
    try:
        return await _get_binding(db, payment_binding_id)
    finally:
        await db.close()


async def _get_binding(db, binding_id: str) -> dict:
    cursor = await db.execute(
        "SELECT * FROM payment_bindings WHERE payment_binding_id = ?",
        (binding_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise AppError(
            ErrorCode.PAYMENT_BINDING_INVALID,
            f"支付绑定未找到: {binding_id}",
        )
    data = dict(row)
    if data["status"] != "ACTIVE":
        raise AppError(
            ErrorCode.PAYMENT_BINDING_INVALID,
            f"支付绑定状态异常: {data['status']}",
        )
    return data
