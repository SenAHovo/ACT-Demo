"""
核心数据对象模块

所有核心数据对象的 Pydantic 模型定义。
覆盖设计方案第9节中的全部 15 个数据对象。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# 9.1 AgentIdentityRecord
# ============================================================
class AgentIdentityRecord(BaseModel):
    agent_id: str
    agent_id_scheme: str = "demo"
    credential_id: str
    public_key: str  # PEM 格式
    credential_status: str = "ACTIVE"  # ACTIVE | SUSPENDED | REVOKED | EXPIRED
    service_endpoint: str | None = None
    issued_at: datetime
    expires_at: datetime | None = None


# ============================================================
# 9.2 UserAgentBinding（详见 shared/bindings.py）
# ============================================================

# ============================================================
# 9.3 PaymentBinding（详见 shared/bindings.py）
# ============================================================

# ============================================================
# 9.4 AuthenticationAssertion
# ============================================================
class AuthenticationAssertion(BaseModel):
    assertion_id: str
    subject_agent_id: str
    verifier_agent_id: str
    credential_id: str
    session_id: str
    authenticated_at: datetime
    expires_at: datetime
    signature: str  # Base64URL


# ============================================================
# 9.5 ISR — Intent Structured Record
# ============================================================
class ISR(BaseModel):
    intent_id: str
    task_goal: str
    delegation_mode: str = "BOUNDED"  # BOUNDED
    validity_start_time: datetime
    validity_end_time: datetime
    max_total_amount: Decimal
    max_single_amount: Decimal
    currency: str = "CNY"
    allowed_sellers: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    allowed_payment_methods: list[str] = Field(default_factory=list)
    agent_id: str
    agent_id_scheme: str = "demo"
    user_agent_binding_id: str
    confirmation_timestamp: datetime


# ============================================================
# 9.6 IAC — Intent Authorization Credential
# ============================================================
class IAC(BaseModel):
    delegation_id: str
    intent_id: str
    delegator_id: str
    agent_id: str
    agent_id_scheme: str = "demo"
    user_agent_binding_id: str
    delegation_mode: str = "BOUNDED"
    validity_start_time: datetime
    validity_end_time: datetime
    max_total_amount: Decimal
    max_single_amount: Decimal
    currency: str = "CNY"
    allowed_sellers: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    allowed_payment_methods: list[str] = Field(default_factory=list)
    source_isr_digest: str  # SHA-256 of ISR
    status_reference: str  # URL to status endpoint
    proof: str  # Base64URL signature


# ============================================================
# 9.7 ServiceOffer
# ============================================================
class ServiceOffer(BaseModel):
    service_id: str
    skill_id: str
    name: str
    category: str
    description: str = ""
    price: Decimal
    currency: str = "CNY"
    availability: str = "ACTIVE"
    price_valid_until: datetime | None = None
    input_schema_url: str | None = None
    output_schema_url: str | None = None
    seller_id: str
    seller_id_scheme: str = "demo"
    estimated_delivery_time: str | None = None


# ============================================================
# 9.8 InteractionEnvelope（详见 shared/interaction.py）
# ============================================================

# ============================================================
# 9.9 ServiceInvocation
# ============================================================
class ServiceInvocation(BaseModel):
    invoke_id: str
    session_id: str
    task_id: str
    message_id: str
    service_id: str
    input: dict[str, Any]
    input_digest: str  # SHA-256
    buyer_agent_id: str
    seller_agent_id: str
    delegation_id: str
    created_at: datetime


# ============================================================
# 9.10 PaymentNeeded（HTTP 402 响应头）
# ============================================================
class PaymentNeeded(BaseModel):
    method_id: str
    psp_id: str
    endpoint: str
    out_trade_no: str
    amount: Decimal
    currency: str = "CNY"
    resource_id: str
    resource_digest: str
    pay_before: datetime
    seller_unique_id: str
    buyer_unique_id: str
    service_id: str
    service_category: str
    session_id: str
    task_id: str


# ============================================================
# 9.11 PaymentRequest
# ============================================================
class PaymentRequest(BaseModel):
    request_id: str
    request_timestamp: datetime
    session_id: str
    task_id: str
    delegation_id: str
    user_agent_binding_id: str
    payment_binding_id: str
    agent_credential_ref: str  # credential_id
    iac: dict[str, Any]  # IAC 序列化
    sub_account_id: str
    out_trade_no: str
    resource_id: str
    resource_digest: str
    service_id: str
    service_category: str
    seller_id: str
    buyer_agent_id: str
    amount: Decimal
    currency: str = "CNY"
    method_id: str
    signature: str  # Base64URL


# ============================================================
# 9.12 PaymentProof
# ============================================================
class PaymentProof(BaseModel):
    payment_proof: str  # proof identifier
    trade_no: str
    out_trade_no: str
    session_id: str
    task_id: str
    resource_id: str
    resource_digest: str
    service_id: str
    seller_id: str
    buyer_agent_id: str
    amount: Decimal
    currency: str = "CNY"
    status: str = "SUCCESS"  # SUCCESS | VOID
    issued_at: datetime
    expires_at: datetime
    psp_id: str
    signature: str  # Base64URL


# ============================================================
# 9.13 ServiceArtifact
# ============================================================
class ServiceArtifact(BaseModel):
    artifact_id: str
    artifact_type: str  # industry_data | industry_analysis | industry_report
    session_id: str
    task_id: str
    source_artifact_ids: list[str] = Field(default_factory=list)
    source_digests: list[str] = Field(default_factory=list)
    content_digest: str  # SHA-256
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    producer_agent_id: str
    service_id: str
    trade_no: str


# ============================================================
# 9.14 AttestationRecord
# ============================================================
class AttestationRecord(BaseModel):
    attestation_id: str
    record_version: int = 1
    event_type: str  # act:* or demo:*
    event_time: datetime
    record_created_at: datetime
    intent_id: str | None = None
    delegation_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    out_trade_no: str | None = None
    trade_no: str | None = None
    upstream_attestation_ids: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    source_record_ref: str | None = None  # 原始记录定位引用
    salt: str  # 随机盐
    payload_hash: str  # SHA-256
    hash_algorithm: str = "SHA-256"
    event_body_or_digest: dict[str, Any] | str  # 事件体或摘要
    signer_id: str
    signature_algorithm: str = "Ed25519"
    signature: str  # Base64URL


# ============================================================
# 9.15 TaskBill
# ============================================================
class TaskBillPayment(BaseModel):
    """任务账单中的单笔支付记录。"""
    trade_no: str
    out_trade_no: str
    service_id: str
    service_name: str
    amount: Decimal
    currency: str = "CNY"


class TaskBill(BaseModel):
    task_id: str
    session_id: str
    intent_id: str
    delegation_id: str
    payments: list[TaskBillPayment] = Field(default_factory=list)
    service_artifacts: list[str] = Field(default_factory=list)  # artifact_id 列表
    total_amount: Decimal = Decimal("0")
    currency: str = "CNY"
    task_status: str  # COMPLETED | PARTIAL | FAILED
    created_at: datetime
    completed_at: datetime | None = None
