"""
IAC 生命周期管理模块

管理 Active / Suspended / Revoked / Expired 状态转换。
暂停或吊销不回滚已经完成的支付和履约。
"""

from __future__ import annotations

from shared.time_utils import utc_now, to_iso, from_iso, is_expired
from shared.errors import ErrorCode, AppError
from .database import get_db


async def get_delegation(delegation_id: str) -> dict:
    """获取 IAC 记录。"""
    db = await get_db()
    try:
        row = await _get_row(db, delegation_id)
        return dict(row)
    finally:
        await db.close()


async def get_delegation_status(delegation_id: str) -> str:
    """获取 IAC 当前状态。"""
    db = await get_db()
    try:
        row = await _get_row(db, delegation_id)
        return row["status"]
    finally:
        await db.close()


async def _get_row(db, delegation_id: str):
    cursor = await db.execute(
        "SELECT * FROM delegations WHERE delegation_id = ?", (delegation_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise AppError(ErrorCode.INVALID_IAC, f"IAC 未找到: {delegation_id}")
    return row


async def _change_status(delegation_id: str, new_status: str, reason: str = "") -> None:
    """变更 IAC 状态并写入历史。"""
    db = await get_db()
    try:
        row = await _get_row(db, delegation_id)
        old_status = row["status"]
        now_iso = to_iso(utc_now())

        await db.execute(
            "UPDATE delegations SET status = ? WHERE delegation_id = ?",
            (new_status, delegation_id),
        )
        await db.execute(
            """INSERT INTO delegation_status_history
               (delegation_id, old_status, new_status, changed_at, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (delegation_id, old_status, new_status, now_iso, reason),
        )
        await db.commit()
    finally:
        await db.close()


async def suspend_delegation(delegation_id: str, reason: str = "") -> dict:
    """暂停 IAC。"""
    row = await get_delegation(delegation_id)
    if row["status"] != "Active":
        raise AppError(
            ErrorCode.IAC_SUSPENDED if row["status"] == "Suspended" else ErrorCode.IAC_REVOKED,
            f"无法暂停: 当前状态为 {row['status']}",
        )
    await _change_status(delegation_id, "Suspended", reason)
    return await get_delegation(delegation_id)


async def resume_delegation(delegation_id: str, reason: str = "") -> dict:
    """恢复 IAC。"""
    row = await get_delegation(delegation_id)
    if row["status"] != "Suspended":
        raise AppError(ErrorCode.IAC_SUSPENDED, f"无法恢复: 当前状态为 {row['status']}")
    # 恢复前检查过期
    if row.get("validity_end_time") and is_expired(from_iso(row["validity_end_time"])):
        await _change_status(delegation_id, "Expired", "有效期已过，自动过期")
        raise AppError(ErrorCode.IAC_EXPIRED, "IAC 已过期，无法恢复")
    await _change_status(delegation_id, "Active", reason)
    return await get_delegation(delegation_id)


async def revoke_delegation(delegation_id: str, reason: str = "") -> dict:
    """吊销 IAC（不可逆）。"""
    row = await get_delegation(delegation_id)
    if row["status"] in ("Revoked", "Expired"):
        raise AppError(ErrorCode.IAC_REVOKED, f"无法吊销: 当前状态为 {row['status']}")
    await _change_status(delegation_id, "Revoked", reason)
    return await get_delegation(delegation_id)


async def check_and_expire(delegation_id: str) -> None:
    """检查并自动过期。"""
    row = await get_delegation(delegation_id)
    if row["status"] in ("Revoked", "Expired"):
        return
    if row.get("validity_end_time") and is_expired(from_iso(row["validity_end_time"])):
        await _change_status(delegation_id, "Expired", "有效期已过，自动过期")
