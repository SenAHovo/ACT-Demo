"""
IAC 签发器模块

根据 ISR 签发 BOUNDED 模式 IAC（意图授权凭证），使用独立密钥签名。
买方智能体不得持有 IAC 签发私钥。
"""

from __future__ import annotations

import uuid
import json

from shared.signatures import (
    generate_keypair,
    private_key_to_pem,
    public_key_to_pem,
    sign_json,
    compute_sha256_digest,
)
from shared.time_utils import utc_now, to_iso, minutes_from_now
from shared.errors import ErrorCode, AppError
from .database import get_db
from .intent_service import get_intent


class IACIssuer:
    """IAC 签发器，持有独立的签发密钥。"""

    def __init__(self):
        self._private_key, self._public_key = generate_keypair()

    @property
    def public_key_pem(self) -> str:
        return public_key_to_pem(self._public_key)

    def sign_attestation(self, data: dict) -> str:
        """对存证数据进行 Ed25519 签名，返回 Base64URL 签名字符串。

        签名覆盖除 signature 外的所有字段，确保存证记录的完整性
        和不可伪造性。
        """
        payload = {k: v for k, v in data.items() if k != "signature"}
        return sign_json(self._private_key, payload)

    def issue(self, intent: dict) -> dict:
        """
        根据已确认的 ISR 签发 IAC。

        Args:
            intent: 从数据库读取的意图记录（dict）

        Returns:
            IAC 字典（含签名 proof）
        """
        # 校验 intent 基本字段
        if not intent.get("intent_id"):
            raise AppError(ErrorCode.INTENT_NOT_CONFIRMED, "意图 ID 缺失")

        delegation_id = f"del_{uuid.uuid4().hex[:16]}"

        # 构建 IAC 载荷
        iac_payload = {
            "delegation_id": delegation_id,
            "intent_id": intent["intent_id"],
            "delegator_id": intent.get("delegator_id", ""),
            "agent_id": intent["agent_id"],
            "agent_id_scheme": intent.get("agent_id_scheme", "demo"),
            "user_agent_binding_id": intent["user_agent_binding_id"],
            "delegation_mode": "BOUNDED",
            "validity_start_time": intent["validity_start_time"],
            "validity_end_time": intent["validity_end_time"],
            "max_total_amount": intent["max_total_amount"],
            "max_single_amount": intent["max_single_amount"],
            "currency": intent.get("currency", "CNY"),
            "allowed_sellers": json.loads(intent.get("allowed_sellers", "[]")),
            "allowed_categories": json.loads(intent.get("allowed_categories", "[]")),
            "allowed_payment_methods": json.loads(intent.get("allowed_payment_methods", "[]")),
            "source_isr_digest": compute_sha256_digest(intent),
            "status_reference": f"http://127.0.0.1:8000/v1/delegations/{delegation_id}",
        }

        # 签名
        proof = sign_json(self._private_key, iac_payload)
        iac_payload["proof"] = proof

        return iac_payload

    async def issue_and_store(self, intent_id: str) -> dict:
        """根据 intent_id 签发 IAC 并入库。"""
        intent = await get_intent(intent_id)
        iac = self.issue(intent)

        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO delegations
                   (delegation_id, intent_id, delegator_id, agent_id, agent_id_scheme,
                    user_agent_binding_id, delegation_mode, validity_start_time,
                    validity_end_time, max_total_amount, max_single_amount, currency,
                    allowed_sellers, allowed_categories, allowed_payment_methods,
                    source_isr_digest, status_reference, status, proof)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?)""",
                (
                    iac["delegation_id"],
                    iac["intent_id"],
                    iac["delegator_id"],
                    iac["agent_id"],
                    iac["agent_id_scheme"],
                    iac["user_agent_binding_id"],
                    iac["delegation_mode"],
                    iac["validity_start_time"],
                    iac["validity_end_time"],
                    iac["max_total_amount"],
                    iac["max_single_amount"],
                    iac["currency"],
                    json.dumps(iac["allowed_sellers"]),
                    json.dumps(iac["allowed_categories"]),
                    json.dumps(iac["allowed_payment_methods"]),
                    iac["source_isr_digest"],
                    iac["status_reference"],
                    iac["proof"],
                ),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM delegations WHERE delegation_id = ?",
                (iac["delegation_id"],),
            )
            row = await cursor.fetchone()
            return dict(row)
        finally:
            await db.close()


# 全局签发器实例
_issuer: IACIssuer | None = None


def get_issuer() -> IACIssuer:
    global _issuer
    if _issuer is None:
        _issuer = IACIssuer()
    return _issuer
