"""
本地余额支付适配器

通过 SQLite 事务实现模拟余额扣款。
"""

from __future__ import annotations

from decimal import Decimal

from ..database import get_db
from ..provider_adapter import PaymentProviderAdapter


class LocalBalanceAdapter(PaymentProviderAdapter):
    """本地余额支付适配器，模拟余额扣款。"""

    async def authorize(
        self,
        sub_account_id: str,
        amount: Decimal,
        currency: str,
        out_trade_no: str,
    ) -> dict:
        db = await get_db()
        try:
            # 查账户
            cursor = await db.execute(
                "SELECT balance, currency, status FROM sub_accounts WHERE sub_account_id = ?",
                (sub_account_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return {"success": False, "trade_no": "", "reason": "子账户不存在"}

            if row["status"] != "ACTIVE":
                return {"success": False, "trade_no": "", "reason": f"账户状态: {row['status']}"}

            current_balance = Decimal(row["balance"])
            if amount > current_balance:
                return {
                    "success": False,
                    "trade_no": "",
                    "reason": f"余额不足: {current_balance} < {amount}",
                }

            new_balance = current_balance - amount

            await db.execute(
                "UPDATE sub_accounts SET balance = ? WHERE sub_account_id = ?",
                (str(new_balance), sub_account_id),
            )
            await db.commit()

            import uuid
            trade_no = f"trade_{uuid.uuid4().hex[:16]}"
            return {"success": True, "trade_no": trade_no, "new_balance": new_balance}
        finally:
            await db.close()

    async def query(self, out_trade_no: str) -> dict | None:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM payments WHERE out_trade_no = ?", (out_trade_no,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await db.close()

    async def verify_proof(self, proof_data: dict) -> dict:
        """验证支付凭证（由 proof_service 处理，此处为接口实现）。"""
        return {"valid": True, "reason": ""}

    async def notify_fulfillment(self, trade_no: str) -> None:
        db = await get_db()
        try:
            from shared.time_utils import utc_now, to_iso
            now = to_iso(utc_now())
            await db.execute(
                "UPDATE payments SET trade_status = 'TRADE_FINISHED', fulfilled_at = ? WHERE trade_no = ?",
                (now, trade_no),
            )
            await db.commit()
        finally:
            await db.close()
