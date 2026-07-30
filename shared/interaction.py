"""
交互信封模块

买卖双方业务请求和响应的统一交互信封（InteractionEnvelope），
用于映射 GB/Z 185.6 的会话、任务、消息和数据语义。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DataItem(BaseModel):
    """交互信封中的数据项。"""
    content_type: str = "application/json"
    metadata: dict[str, str] = Field(default_factory=dict)
    payload: Any = None


class ArtifactRef(BaseModel):
    """交互信封中的 Artifact 引用。"""
    artifact_id: str
    artifact_type: str
    content_digest: str


class InteractionEnvelope(BaseModel):
    """统一交互信封。

    ACT 的 Payment-Needed、Payment-Proof 和 Payment-Validation 仍通过
    HTTP 头承载，不与交互信封相互替代。
    """

    session_id: str
    task_id: str
    message_id: str
    sender_role: str  # "buyer_agent" | "seller_agent"
    sender_id: str
    receiver_id: str
    message_type: str  # "service_invocation" | "service_response" | "authentication" | "task_status"
    task_state: str  # "SUBMITTED" | "PAYMENT_REQUIRED" | "PAID" | "FULFILLED" | "FAILED"
    state_changed_at: str  # ISO 8601 UTC
    data_items: list[DataItem] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    authentication_assertion_ref: str | None = None


def generate_interaction_id(prefix: str) -> str:
    """生成交互标识（session_id / task_id / message_id）。"""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
