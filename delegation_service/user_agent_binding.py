"""
用户-智能体绑定模块

维护委托人与买方智能体的绑定关系。
"""

from __future__ import annotations

from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError
from .database import get_db


async def create_user_agent_binding(
    user_agent_binding_id: str,
    delegator_id: str,
    buyer_agent_id: str,
    authorization_scope: str = "BOUNDED",
    expires_at: str | None = None,
) -> dict:
    """创建委托人-买方智能体绑定。"""
    db = await get_db()
    try:
        now_iso = to_iso(utc_now())
        await db.execute(
            """INSERT OR IGNORE INTO user_agent_bindings
               (user_agent_binding_id, delegator_id, buyer_agent_id,
                authorization_scope, status, created_at, expires_at)
               VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)""",
            (user_agent_binding_id, delegator_id, buyer_agent_id,
             authorization_scope, now_iso, expires_at),
        )
        await db.commit()
        return await _get_binding(db, user_agent_binding_id)
    finally:
        await db.close()


async def get_user_agent_binding(user_agent_binding_id: str) -> dict:
    """获取委托人-智能体绑定。"""
    db = await get_db()
    try:
        return await _get_binding(db, user_agent_binding_id)
    finally:
        await db.close()


async def _get_binding(db, binding_id: str) -> dict:
    cursor = await db.execute(
        "SELECT * FROM user_agent_bindings WHERE user_agent_binding_id = ?",
        (binding_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise AppError(
            ErrorCode.USER_AGENT_BINDING_INVALID,
            f"绑定未找到: {binding_id}",
        )
    data = dict(row)
    if data["status"] != "ACTIVE":
        raise AppError(
            ErrorCode.USER_AGENT_BINDING_INVALID,
            f"绑定状态异常: {data['status']}",
        )
    return data
