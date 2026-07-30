"""
支付提供方适配器接口

统一支付接口，隔离具体支付实现。
当前实现: LocalBalanceAdapter
未来扩展: APOPAdapter
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentProviderAdapter(ABC):
    """支付提供方适配器抽象接口。"""

    @abstractmethod
    async def authorize(
        self,
        sub_account_id: str,
        amount: Decimal,
        currency: str,
        out_trade_no: str,
    ) -> dict:
        """执行支付授权（扣款）。

        Returns:
            {"success": bool, "trade_no": str, "new_balance": Decimal}
        """
        ...

    @abstractmethod
    async def query(self, out_trade_no: str) -> dict | None:
        """查询支付状态。"""
        ...

    @abstractmethod
    async def verify_proof(self, proof_data: dict) -> dict:
        """验证支付凭证。

        Returns:
            {"valid": bool, "reason": str}
        """
        ...

    @abstractmethod
    async def notify_fulfillment(self, trade_no: str) -> None:
        """通知履约完成。"""
        ...
