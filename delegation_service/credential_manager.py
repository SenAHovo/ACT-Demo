"""
凭证管理器模块

为各参与方生成 Ed25519 本地凭证，维护凭证的有效、暂停、吊销和过期状态。
"""

from __future__ import annotations

from shared.signatures import generate_keypair, private_key_to_pem, public_key_to_pem
from shared.identity import generate_credential_id
from shared.time_utils import utc_now, to_iso, minutes_from_now
from .identity_registry import register_identity


async def create_credential(
    agent_id: str,
    agent_id_scheme: str = "demo",
    service_endpoint: str | None = None,
    validity_days: int = 365,
) -> dict:
    """
    为智能体创建 Ed25519 凭证并注册身份。

    Returns:
        {
            "agent_id": ...,
            "credential_id": ...,
            "public_key_pem": ...,
            "private_key_pem": ...,
        }
    """
    private_key, public_key = generate_keypair()
    credential_id = generate_credential_id()
    pub_pem = public_key_to_pem(public_key)
    priv_pem = private_key_to_pem(private_key)

    expires_at = minutes_from_now(validity_days * 24 * 60)
    expires_iso = to_iso(expires_at)

    await register_identity(
        agent_id=agent_id,
        agent_id_scheme=agent_id_scheme,
        credential_id=credential_id,
        public_key=pub_pem,
        service_endpoint=service_endpoint,
        expires_at=expires_iso,
    )

    return {
        "agent_id": agent_id,
        "agent_id_scheme": agent_id_scheme,
        "credential_id": credential_id,
        "public_key_pem": pub_pem,
        "private_key_pem": priv_pem,
    }
