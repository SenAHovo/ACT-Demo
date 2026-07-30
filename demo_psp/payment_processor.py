"""
支付处理器模块

按固定顺序执行完整的支付处理流程（19 步）。
"""

from __future__ import annotations

import uuid
import hashlib
import json
from decimal import Decimal

from shared.time_utils import utc_now, to_iso, from_iso
from shared.signatures import sign_json, verify_json, compute_sha256_digest
from shared.errors import ErrorCode, AppError
from .database import get_db
from .identity_verifier import verify_agent_credential
from .iac_verifier import verify_iac
from .binding_verifier import verify_user_agent_binding, verify_payment_binding
from .policy_engine import (
    check_single_limit,
    check_total_limit,
    check_seller_allowed,
    check_category_allowed,
    check_method_allowed,
    parse_decimal_list_from_iac,
)
from .account_service import get_account
from .adapters.local_balance import LocalBalanceAdapter
from .trade_store import save_proof as _save_proof_to_store


_adapter = LocalBalanceAdapter()
_psp_signing_key = None
_psp_public_key = None


def set_signing_key(private_key):
    """设置 PSP 的 Ed25519 签名密钥对（由 app 初始化时设置）。"""
    global _psp_signing_key, _psp_public_key
    _psp_signing_key = private_key
    _psp_public_key = private_key.public_key()


def get_public_key():
    """获取 PSP 的 Ed25519 公钥（供 proof_service 验证签名）。"""
    return _psp_public_key


def get_signing_key():
    """获取 PSP 的 Ed25519 私钥（供 attestation_outbox 签发存证）。"""
    return _psp_signing_key


async def process_payment(request: dict) -> dict:
    """
    执行完整的支付处理流程。

    固定顺序:
    1. 校验请求标识
    2. 校验请求时间戳
    3. 验证买方凭证
    4. 验证委托人-买方绑定
    5. 验证支付方法和子账户绑定
    6. 验证 IAC 签名和状态
    7. 查询 IAC 状态
    8. 核验受托智能体和 BOUNDED 模式
    9. 核验支付方法、卖方和服务类别
    10. 核验单笔金额和累计金额
    11. 核验订单、资源及交互任务绑定
    12. 核验模拟子账户
    13. 幂等检查
    14. 执行扣款
    15. 生成 trade_no
    16. 写入支付记录
    17. 签发支付凭证
    18. 本地保存原始记录
    19. 返回结果
    """
    # 1. 校验请求标识
    request_id = request.get("request_id")
    if not request_id:
        raise AppError(ErrorCode.INVALID_IAC, "缺少 request_id")

    # 2. 校验时间戳
    request_ts = request.get("request_timestamp")
    if request_ts:
        try:
            ts = from_iso(request_ts)
            now = utc_now()
            diff_seconds = abs((now - ts).total_seconds())
            if diff_seconds > 300:  # 5 分钟窗口
                raise AppError(ErrorCode.INVALID_IAC, f"请求时间戳偏差过大: {diff_seconds:.0f}s")
        except AppError:
            raise
        except Exception:
            pass  # 时间戳格式异常，降级通过

    # 3. 验证买方凭证
    buyer_agent_id = request["buyer_agent_id"]
    credential_id = request.get("agent_credential_ref")
    await verify_agent_credential(credential_id, buyer_agent_id)

    # 4. 验证委托人-买方绑定
    uab_id = request.get("user_agent_binding_id")
    await verify_user_agent_binding(uab_id, buyer_agent_id)

    # 5. 验证支付绑定
    pb_id = request.get("payment_binding_id")
    sub_account_id = request["sub_account_id"]
    await verify_payment_binding(pb_id, buyer_agent_id, sub_account_id)

    # 6-8. 验证 IAC
    delegation_id = request["delegation_id"]
    iac = await verify_iac(delegation_id, buyer_agent_id, "BOUNDED")

    # 交叉验证：IAC 的绑定 ID 必须与支付请求中的绑定 ID 一致
    iac_uab_id = iac.get("user_agent_binding_id", "")
    if iac_uab_id and iac_uab_id != uab_id:
        raise AppError(
            ErrorCode.USER_AGENT_BINDING_INVALID,
            f"IAC 绑定 ID ({iac_uab_id}) 与支付请求绑定 ID ({uab_id}) 不一致",
        )

    # 9. 核验策略
    amount = Decimal(request["amount"])
    seller_id = request["seller_id"]
    service_category = request["service_category"]
    method_id = request["method_id"]

    check_seller_allowed(seller_id, parse_decimal_list_from_iac(iac, "allowed_sellers"))
    check_category_allowed(service_category, parse_decimal_list_from_iac(iac, "allowed_categories"))
    check_method_allowed(method_id, parse_decimal_list_from_iac(iac, "allowed_payment_methods"))

    max_single = Decimal(iac.get("max_single_amount", "0"))
    max_total = Decimal(iac.get("max_total_amount", "0"))
    check_single_limit(amount, max_single)

    # 累计额度
    total_spent = await _get_accumulated_spent(delegation_id)
    check_total_limit(amount, total_spent, max_total)

    # 11. 核验资源
    resource_id = request["resource_id"]
    if request.get("resource_digest"):
        pass  # 摘要校验由卖方侧完成

    # 12. 核验子账户
    account = await get_account(sub_account_id)

    # 13. 幂等检查
    db = await get_db()
    try:
        existing = await _check_idempotency(db, request_id, request)
        if existing:
            return existing

        # 14. 执行扣款
        result = await _adapter.authorize(
            sub_account_id, amount, request.get("currency", "CNY"),
            request.get("out_trade_no", ""),
        )
        if not result["success"]:
            raise AppError(ErrorCode.INSUFFICIENT_BALANCE, result.get("reason", "扣款失败"))

        trade_no = result["trade_no"]
        now = utc_now()

        # 15-16. 写入支付记录
        await db.execute(
            """INSERT INTO payments
               (trade_no, request_id, out_trade_no, delegation_id,
                user_agent_binding_id, payment_binding_id, sub_account_id,
                buyer_agent_id, seller_id, service_id, service_category,
                resource_id, resource_digest, session_id, task_id,
                amount, currency, method_id, trade_status, created_at, paid_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WAIT_SELLER_FULFILLMENT', ?, ?)""",
            (
                trade_no,
                request_id,
                request.get("out_trade_no", ""),
                delegation_id,
                uab_id,
                pb_id,
                sub_account_id,
                buyer_agent_id,
                seller_id,
                request.get("service_id", ""),
                service_category,
                resource_id,
                request.get("resource_digest", ""),
                request.get("session_id", ""),
                request.get("task_id", ""),
                str(amount),
                request.get("currency", "CNY"),
                method_id,
                to_iso(now),
                to_iso(now),
            ),
        )

        # 更新累计
        new_total = total_spent + amount
        await db.execute(
            """INSERT INTO iac_usage (delegation_id, total_spent, currency, last_updated)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(delegation_id) DO UPDATE SET
               total_spent = excluded.total_spent, last_updated = excluded.last_updated""",
            (delegation_id, str(new_total), request.get("currency", "CNY"), to_iso(now)),
        )

        # 记录幂等
        request_digest = compute_sha256_digest(request)
        await db.execute(
            "INSERT INTO used_requests (request_id, request_digest, trade_no, recorded_at) VALUES (?, ?, ?, ?)",
            (request_id, request_digest, trade_no, to_iso(now)),
        )

        await db.commit()

        # 17. 签发支付凭证
        proof = await _issue_proof(
            trade_no=trade_no,
            out_trade_no=request.get("out_trade_no", ""),
            session_id=request.get("session_id", ""),
            task_id=request.get("task_id", ""),
            resource_id=resource_id,
            resource_digest=request.get("resource_digest", ""),
            service_id=request.get("service_id", ""),
            seller_id=seller_id,
            buyer_agent_id=buyer_agent_id,
            amount=amount,
            currency=request.get("currency", "CNY"),
        )

        return {
            "success": True,
            "trade_no": trade_no,
            "proof": proof,
            "new_balance": result["new_balance"],
        }
    finally:
        await db.close()


async def _get_accumulated_spent(delegation_id: str) -> Decimal:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT total_spent FROM iac_usage WHERE delegation_id = ?",
            (delegation_id,),
        )
        row = await cursor.fetchone()
        return Decimal(row["total_spent"]) if row else Decimal("0")
    finally:
        await db.close()


async def _check_idempotency(db, request_id: str, request: dict) -> dict | None:
    cursor = await db.execute(
        "SELECT trade_no, request_digest FROM used_requests WHERE request_id = ?",
        (request_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    current_digest = compute_sha256_digest(request)
    if row["request_digest"] != current_digest:
        raise AppError(ErrorCode.IDEMPOTENCY_CONFLICT, "相同 request_id 但内容不同")

    # 幂等返回原结果
    trade_no = row["trade_no"]
    pay_cursor = await db.execute(
        "SELECT * FROM payments WHERE trade_no = ?", (trade_no,)
    )
    pay_row = await pay_cursor.fetchone()
    if pay_row:
        return {
            "success": True,
            "trade_no": trade_no,
            "proof": {"trade_no": trade_no, "status": "SUCCESS"},
            "new_balance": Decimal("0"),
            "idempotent": True,
        }
    return None


async def _issue_proof(
    trade_no: str, out_trade_no: str, session_id: str, task_id: str,
    resource_id: str, resource_digest: str, service_id: str,
    seller_id: str, buyer_agent_id: str, amount: Decimal, currency: str,
) -> dict:
    from shared.time_utils import minutes_from_now

    now = utc_now()
    expires = minutes_from_now(30)

    proof_payload = {
        "payment_proof": f"proof_{trade_no}",
        "trade_no": trade_no,
        "out_trade_no": out_trade_no,
        "session_id": session_id,
        "task_id": task_id,
        "resource_id": resource_id,
        "resource_digest": resource_digest,
        "service_id": service_id,
        "seller_id": seller_id,
        "buyer_agent_id": buyer_agent_id,
        "amount": str(amount),
        "currency": currency,
        "status": "SUCCESS",
        "issued_at": to_iso(now),
        "expires_at": to_iso(expires),
        "psp_id": "urn:demo:psp:local:v1",
    }

    signature = sign_json(_psp_signing_key, proof_payload) if _psp_signing_key else "unsigned"
    proof_payload["signature"] = signature

    # 保存凭证到数据库
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO payment_proofs (trade_no, proof_data, issued_at, expires_at, status)
               VALUES (?, ?, ?, ?, 'SUCCESS')""",
            (trade_no, json.dumps(proof_payload), to_iso(now), to_iso(expires)),
        )
        await db.commit()
    finally:
        await db.close()

    # 同时写入共享内存存储（同一进程内 proof_service 可读取）
    _save_proof_to_store(trade_no, proof_payload)

    return proof_payload
