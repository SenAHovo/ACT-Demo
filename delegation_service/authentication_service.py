"""
认证服务模块

验证对方凭证，产生简化的 AuthenticationAssertion。
模拟 GB/Z 185.3 身份鉴别流程，不建立外部受信证书链。
"""

from __future__ import annotations

import uuid

from shared.time_utils import utc_now, to_iso, minutes_from_now, from_iso, is_expired
from shared.signatures import load_public_key, verify_json
from shared.errors import ErrorCode, AppError
from .database import get_db
from .identity_registry import get_identity, get_credential_status


async def authenticate(
    subject_agent_id: str,
    verifier_agent_id: str,
    credential_id: str,
    challenge: dict,
    signature_b64: str,
) -> dict:
    """
    验证智能体凭证并生成 AuthenticationAssertion。

    Args:
        subject_agent_id: 被验证方 agent_id
        verifier_agent_id: 验证方 agent_id
        credential_id: 被验证方的凭证 ID
        challenge: JCS 规范化后的挑战对象
        signature_b64: Base64URL 签名

    Returns:
        AuthenticationAssertion 字典
    """
    # 1. 查身份
    identity = await get_identity(subject_agent_id)

    # 2. 核凭证 ID
    if identity["credential_id"] != credential_id:
        raise AppError(
            ErrorCode.INVALID_CREDENTIAL,
            f"凭证 ID 不匹配: {credential_id}",
        )

    # 3. 核凭证状态
    status = identity["credential_status"]
    if status != "ACTIVE":
        raise AppError(
            ErrorCode.AUTHENTICATION_FAILED,
            f"凭证状态异常: {status}",
        )

    # 4. 核过期
    if identity.get("expires_at"):
        if is_expired(from_iso(identity["expires_at"])):
            raise AppError(ErrorCode.CREDENTIAL_EXPIRED)

    # 5. 验签
    public_key = load_public_key(identity["public_key"])
    if not verify_json(public_key, challenge, signature_b64):
        raise AppError(ErrorCode.AUTHENTICATION_FAILED, "签名验证失败")

    # 6. 生成断言
    now = utc_now()
    assertion_id = f"assert_{uuid.uuid4().hex[:16]}"
    session_id = f"session_{uuid.uuid4().hex[:16]}"

    db = await get_db()
    try:
        expires_at = minutes_from_now(30)
        await db.execute(
            """INSERT INTO authentication_assertions
               (assertion_id, subject_agent_id, verifier_agent_id,
                credential_id, session_id, authenticated_at, expires_at, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (assertion_id, subject_agent_id, verifier_agent_id,
             credential_id, session_id, to_iso(now), to_iso(expires_at), signature_b64),
        )
        await db.commit()

        return {
            "assertion_id": assertion_id,
            "subject_agent_id": subject_agent_id,
            "verifier_agent_id": verifier_agent_id,
            "credential_id": credential_id,
            "session_id": session_id,
            "authenticated_at": to_iso(now),
            "expires_at": to_iso(expires_at),
            "signature": signature_b64,
        }
    finally:
        await db.close()


async def verify_assertion(assertion_id: str) -> dict:
    """验证已存在的认证断言是否有效。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM authentication_assertions WHERE assertion_id = ?",
            (assertion_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.AUTHENTICATION_FAILED, "断言未找到")

        data = dict(row)
        if data.get("expires_at") and is_expired(from_iso(data["expires_at"])):
            raise AppError(ErrorCode.AUTHENTICATION_FAILED, "断言已过期")

        return data
    finally:
        await db.close()
