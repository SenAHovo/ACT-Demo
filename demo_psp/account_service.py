"""
账户服务模块

管理模拟子账户的余额、状态和余额变化记录。
"""

from __future__ import annotations

from decimal import Decimal

from .database import get_db


async def create_sub_account(
    sub_account_id: str,
    buyer_agent_id: str,
    payment_binding_id: str,
    initial_balance: Decimal | str = "5.00",
) -> dict:
    """创建模拟子账户。"""
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR IGNORE INTO sub_accounts
               (sub_account_id, buyer_agent_id, payment_binding_id, balance)
               VALUES (?, ?, ?, ?)""",
            (sub_account_id, buyer_agent_id, payment_binding_id, str(initial_balance)),
        )
        await db.commit()
        return await get_account(sub_account_id)
    finally:
        await db.close()


async def get_account(sub_account_id: str) -> dict:
    """获取子账户信息。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM sub_accounts WHERE sub_account_id = ?",
            (sub_account_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            from shared.errors import ErrorCode, AppError
            raise AppError(ErrorCode.PAYMENT_NOT_FOUND, f"子账户不存在: {sub_account_id}")
        return dict(row)
    finally:
        await db.close()


async def get_balance(sub_account_id: str) -> Decimal:
    """获取余额。"""
    acct = await get_account(sub_account_id)
    return Decimal(acct["balance"])


async def topup_account(sub_account_id: str, amount: Decimal | str) -> dict:
    """充值指定金额到子账户，返回更新后的账户信息。"""
    db = await get_db()
    try:
        acct = await get_account(sub_account_id)
        current = Decimal(acct["balance"])
        new_balance = current + Decimal(str(amount))
        await db.execute(
            "UPDATE sub_accounts SET balance = ? WHERE sub_account_id = ?",
            (str(new_balance), sub_account_id),
        )
        await db.commit()
        return {"sub_account_id": sub_account_id, "balance": str(new_balance), "added": float(amount)}
    finally:
        await db.close()
