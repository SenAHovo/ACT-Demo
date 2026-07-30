"""
IAC 验证器模块

验证 IAC Ed25519 签名、生命周期、受托智能体、委托模式。
"""

from __future__ import annotations

import os
import httpx

from shared.signatures import verify_json, load_public_key
from shared.time_utils import from_iso, is_expired
from shared.errors import ErrorCode, AppError

DELEGATION_SERVICE_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")

# 缓存委托授权服务的 Ed25519 公钥（启动时加载一次）
_delegation_public_key = None


async def _ensure_public_key():
    """获取并缓存委托授权服务的 Ed25519 签发公钥。"""
    global _delegation_public_key
    if _delegation_public_key is not None:
        return _delegation_public_key

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{DELEGATION_SERVICE_URL}/v1/public-key")
        if resp.status_code != 200:
            raise AppError(ErrorCode.INVALID_IAC, "无法获取委托授权服务公钥")
        pem = resp.json()["public_key"]
        _delegation_public_key = load_public_key(pem)
        return _delegation_public_key


async def verify_iac(
    delegation_id: str,
    expected_agent_id: str,
    expected_mode: str = "BOUNDED",
) -> dict:
    """验证 IAC 有效且匹配受托智能体。

    验证步骤:
      0. 获取签发公钥
      1. 获取 IAC
      2. 校验 Ed25519 签名（防篡改核心步骤）
      3. 检查状态
      4. 检查有效期
      5. 检查受托智能体
      6. 检查委托模式
    """
    try:
        # 0. 获取签发公钥
        issuer_public_key = await _ensure_public_key()

        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. 获取 IAC
            resp = await client.get(
                f"{DELEGATION_SERVICE_URL}/v1/delegations/{delegation_id}"
            )
            if resp.status_code != 200:
                raise AppError(ErrorCode.INVALID_IAC, f"IAC 未找到: {delegation_id}")

            iac = resp.json()

            # 2. 校验 Ed25519 签名 —— 防篡改核心步骤
            proof = iac.get("proof")
            if not proof:
                raise AppError(ErrorCode.INVALID_IAC, "IAC 缺少 proof 签名字段")

            # 构造签名前的原始载荷（去除 proof 和 status，这两个字段是签名后追加的）
            payload_to_verify = {
                k: v for k, v in iac.items()
                if k not in ("proof", "status")
            }
            if not verify_json(issuer_public_key, payload_to_verify, proof):
                raise AppError(ErrorCode.INVALID_IAC, "IAC Ed25519 签名验证失败——凭证可能被篡改")

            # 3. 检查状态
            if iac.get("status") != "Active":
                status = iac.get("status", "unknown")
                if status == "Suspended":
                    raise AppError(ErrorCode.IAC_SUSPENDED)
                elif status == "Revoked":
                    raise AppError(ErrorCode.IAC_REVOKED)
                elif status == "Expired":
                    raise AppError(ErrorCode.IAC_EXPIRED)
                else:
                    raise AppError(ErrorCode.INVALID_IAC, f"IAC 状态: {status}")

            # 4. 检查有效期
            if iac.get("validity_end_time"):
                if is_expired(from_iso(iac["validity_end_time"])):
                    raise AppError(ErrorCode.IAC_EXPIRED)

            # 5. 检查受托智能体
            if iac.get("agent_id") != expected_agent_id:
                raise AppError(
                    ErrorCode.AGENT_ID_MISMATCH,
                    f"IAC agent_id {iac.get('agent_id')} != {expected_agent_id}",
                )

            # 6. 检查委托模式
            if iac.get("delegation_mode") != expected_mode:
                raise AppError(
                    ErrorCode.INVALID_DELEGATION_MODE,
                    f"期望 {expected_mode}，实际 {iac.get('delegation_mode')}",
                )

            return iac
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.INVALID_IAC, f"IAC 验证异常: {e}")
