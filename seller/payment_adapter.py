"""
支付适配器模块

发布支付能力声明、验证支付凭证。
"""

from __future__ import annotations

import os
import httpx

from shared.errors import ErrorCode, AppError

DEMO_PSP_URL = os.getenv("DEMO_PSP_URL", "http://127.0.0.1:8002")
SELLER_ID = "urn:demo:agent:seller:research-service-001"


def get_payment_capability() -> dict:
    """返回卖方支持的支付能力声明。"""
    return {
        "supported_methods": [
            {
                "method_id": "urn:demo:payment:local-balance:v1",
                "name": "本地模拟余额支付",
                "psp_id": "urn:demo:psp:local:v1",
                "currency": "CNY",
                "description": "教学用途，不处理真实资金",
            }
        ],
        "psp_endpoint": f"{DEMO_PSP_URL}/v1/payments",
        "proof_verification_endpoint": f"{DEMO_PSP_URL}/v1/payment-proofs/verify",
    }


async def verify_payment_proof(proof_data: dict, expected_amount: str = "") -> dict:
    """调用 DemoPSP 验证支付凭证，并独立校验卖方身份和金额。

    ACT 规范要求卖方独立验证：
    1. PSP 确认凭证有效（签名、状态、过期）
    2. proof 中的 seller_id 必须等于自身 ID（防止跨卖方凭证重用）
    3. proof 中的 amount 必须等于服务标价
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{DEMO_PSP_URL}/v1/payment-proofs/verify",
                json=proof_data,
            )
            if resp.status_code != 200:
                raise AppError(ErrorCode.PROOF_INVALID, f"PSP 凭证验证失败: {resp.status_code}")
            result = resp.json()
            if not result.get("valid"):
                raise AppError(ErrorCode.PROOF_INVALID, result.get("reason", "凭证无效"))

            # ---- 卖方独立验证 seller_id（防止跨卖方凭证重用） ----
            stored = result.get("stored", {})
            proof_seller_id = stored.get("seller_id", "")
            if proof_seller_id and proof_seller_id != SELLER_ID:
                raise AppError(
                    ErrorCode.PROOF_INVALID,
                    f"凭证卖方 ID ({proof_seller_id}) 与当前卖方 ({SELLER_ID}) 不一致",
                )

            # ---- 卖方独立验证金额（防止少付攻击） ----
            if expected_amount:
                proof_amount = stored.get("amount", "")
                if proof_amount and str(proof_amount) != str(expected_amount):
                    raise AppError(
                        ErrorCode.PROOF_INVALID,
                        f"凭证金额 ({proof_amount}) 与订单金额 ({expected_amount}) 不一致",
                    )

            return result
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.PROOF_INVALID, f"无法连接 PSP: {e}")


async def notify_fulfillment(trade_no: str) -> None:
    """通知 DemoPSP 履约完成。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{DEMO_PSP_URL}/v1/trades/{trade_no}/fulfillment",
                json={"trade_no": trade_no},
            )
    except Exception:
        pass  # 履约通知失败不影响主流程
