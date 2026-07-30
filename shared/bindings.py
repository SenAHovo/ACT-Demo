"""
绑定工具模块

定义 UserAgentBinding 和 PaymentBinding 的数据结构与校验。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserAgentBinding(BaseModel):
    """委托人—买方智能体绑定关系。"""

    user_agent_binding_id: str
    delegator_id: str
    buyer_agent_id: str
    authorization_scope: str = "BOUNDED"
    authentication_method: str = "demo_local_credential"
    status: str = "ACTIVE"
    created_at: datetime
    expires_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        return self.status == "ACTIVE" and (self.expires_at is None or now <= self.expires_at)


class PaymentBinding(BaseModel):
    """买方智能体—支付方法—子账户绑定关系。"""

    payment_binding_id: str
    user_agent_binding_id: str
    buyer_agent_id: str
    payment_method_id: str
    sub_account_id: str
    status: str = "ACTIVE"
    valid_from: datetime
    valid_until: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        if self.status != "ACTIVE":
            return False
        if self.valid_until is None:
            return True
        return now <= self.valid_until
