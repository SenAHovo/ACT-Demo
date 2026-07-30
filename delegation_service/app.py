"""
委托授权、身份与绑定服务 — FastAPI 应用入口

运行端口: 8000
"""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.errors import AppError
from shared.identity import generate_binding_id
from .database import init_db
from .identity_registry import (
    register_identity,
    get_identity,
    get_credential_status,
)
from .credential_manager import create_credential
from .authentication_service import authenticate, verify_assertion
from .user_agent_binding import create_user_agent_binding, get_user_agent_binding
from .payment_binding import create_payment_binding, get_payment_binding
from .intent_service import create_intent, get_intent
from .issuer import get_issuer
from .lifecycle import (
    get_delegation,
    get_delegation_status,
    suspend_delegation,
    resume_delegation,
    revoke_delegation,
)
from .attestation_client import submit_attestation

app = FastAPI(title="Delegation & Identity Service", version="1.0.0")


# ============================================================
# 错误处理
# ============================================================
@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    return JSONResponse(
        status_code=_error_status(exc.code),
        content={"error": exc.code.value, "message": exc.message},
    )


def _error_status(code) -> int:
    if "NOT_FOUND" in code.value:
        return 404
    if "EXPIRED" in code.value:
        return 403
    if "FAILED" in code.value or "INVALID" in code.value:
        return 400
    if "EXCEEDED" in code.value or "INSUFFICIENT" in code.value:
        return 402
    return 500


# ============================================================
# 请求模型
# ============================================================
class CreateIdentityRequest(BaseModel):
    agent_id: str
    agent_id_scheme: str = "demo"
    service_endpoint: str | None = None


class VerifyAuthRequest(BaseModel):
    subject_agent_id: str
    verifier_agent_id: str
    credential_id: str
    challenge: dict
    signature: str


class CreateUserBindingRequest(BaseModel):
    user_agent_binding_id: str
    delegator_id: str
    buyer_agent_id: str
    authorization_scope: str = "BOUNDED"


class CreatePaymentBindingRequest(BaseModel):
    payment_binding_id: str
    user_agent_binding_id: str
    buyer_agent_id: str
    payment_method_id: str
    sub_account_id: str


class CreateIntentRequest(BaseModel):
    task_goal: str
    agent_id: str
    agent_id_scheme: str = "demo"
    user_agent_binding_id: str
    max_total_amount: str = "1.00"
    max_single_amount: str = "0.50"
    currency: str = "CNY"
    allowed_sellers: list[str] = []
    allowed_categories: list[str] = []
    allowed_payment_methods: list[str] = []
    validity_minutes: int = 30
    delegator_id: str = ""


class IssueDelegationRequest(BaseModel):
    intent_id: str


class StatusChangeRequest(BaseModel):
    reason: str = ""


# ============================================================
# 初始化端点
# ============================================================
@app.post("/v1/identities")
async def api_create_identity(req: CreateIdentityRequest):
    """为智能体创建 Ed25519 凭证并注册身份。"""
    result = await create_credential(
        agent_id=req.agent_id,
        agent_id_scheme=req.agent_id_scheme,
        service_endpoint=req.service_endpoint,
    )
    return result


@app.get("/v1/identities/{agent_id}")
async def api_get_identity(agent_id: str):
    """获取智能体身份记录。"""
    return await get_identity(agent_id)


@app.get("/v1/credentials/{credential_id}/status")
async def api_credential_status(credential_id: str):
    """获取凭证状态及归属信息。"""
    return await get_credential_status(credential_id)


# ============================================================
# 认证端点
# ============================================================
@app.post("/v1/authentications/verify")
async def api_verify_authentication(req: VerifyAuthRequest):
    """验证智能体凭证并返回 AuthenticationAssertion。"""
    return await authenticate(
        subject_agent_id=req.subject_agent_id,
        verifier_agent_id=req.verifier_agent_id,
        credential_id=req.credential_id,
        challenge=req.challenge,
        signature_b64=req.signature,
    )


# ============================================================
# 绑定端点
# ============================================================
@app.post("/v1/user-agent-bindings")
async def api_create_user_binding(req: CreateUserBindingRequest):
    """创建委托人-买方智能体绑定。"""
    return await create_user_agent_binding(
        user_agent_binding_id=req.user_agent_binding_id,
        delegator_id=req.delegator_id,
        buyer_agent_id=req.buyer_agent_id,
        authorization_scope=req.authorization_scope,
    )


@app.get("/v1/user-agent-bindings/{binding_id}")
async def api_get_user_binding(binding_id: str):
    """获取委托人-智能体绑定。"""
    return await get_user_agent_binding(binding_id)


@app.post("/v1/payment-bindings")
async def api_create_payment_binding(req: CreatePaymentBindingRequest):
    """创建支付绑定。"""
    return await create_payment_binding(
        payment_binding_id=req.payment_binding_id,
        user_agent_binding_id=req.user_agent_binding_id,
        buyer_agent_id=req.buyer_agent_id,
        payment_method_id=req.payment_method_id,
        sub_account_id=req.sub_account_id,
    )


@app.get("/v1/payment-bindings/{binding_id}")
async def api_get_payment_binding(binding_id: str):
    """获取支付绑定。"""
    return await get_payment_binding(binding_id)


# ============================================================
# 意图与授权端点
# ============================================================
@app.post("/v1/intents")
async def api_create_intent(req: CreateIntentRequest):
    """创建意图结构化记录（ISR）。"""
    result = await create_intent(
        task_goal=req.task_goal,
        agent_id=req.agent_id,
        agent_id_scheme=req.agent_id_scheme,
        user_agent_binding_id=req.user_agent_binding_id,
        max_total_amount=req.max_total_amount,
        max_single_amount=req.max_single_amount,
        currency=req.currency,
        allowed_sellers=req.allowed_sellers,
        allowed_categories=req.allowed_categories,
        allowed_payment_methods=req.allowed_payment_methods,
        validity_minutes=req.validity_minutes,
        delegator_id=req.delegator_id,
    )

    # 异步提交存证
    asyncio.create_task(_submit_intent_event(result))

    return result


async def _submit_intent_event(intent: dict):
    from shared.time_utils import utc_now, to_iso
    from shared.signatures import compute_sha256_digest
    import uuid

    issuer = get_issuer()

    event = {
        "attestation_id": f"att_{uuid.uuid4().hex[:16]}",
        "record_version": 1,
        "event_type": "act:delegation:intent-created",
        "event_time": to_iso(utc_now()),
        "record_created_at": to_iso(utc_now()),
        "intent_id": intent["intent_id"],
        "participants": [intent["agent_id"]],
        "salt": uuid.uuid4().hex[:8],
        "payload_hash": compute_sha256_digest(intent),
        "hash_algorithm": "SHA-256",
        "event_body_or_digest": {"intent_id": intent["intent_id"]},
        "signer_id": "delegation_service",
        "signature_algorithm": "Ed25519",
    }
    # 签发真实 Ed25519 签名，替代 placeholder
    event["signature"] = issuer.sign_attestation(event)
    await submit_attestation(event)


@app.post("/v1/delegations")
async def api_issue_delegation(req: IssueDelegationRequest):
    """签发 IAC（BOUNDED 模式）。"""
    issuer = get_issuer()
    result = await issuer.issue_and_store(req.intent_id)

    # 异步提交存证
    asyncio.create_task(_submit_delegation_event(dict(result)))

    return dict(result)


async def _submit_delegation_event(delegation: dict):
    from shared.time_utils import utc_now, to_iso
    from shared.signatures import compute_sha256_digest
    import uuid

    issuer = get_issuer()

    event = {
        "attestation_id": f"att_{uuid.uuid4().hex[:16]}",
        "record_version": 1,
        "event_type": "act:delegation:delegation-issued",
        "event_time": to_iso(utc_now()),
        "record_created_at": to_iso(utc_now()),
        "intent_id": delegation["intent_id"],
        "delegation_id": delegation["delegation_id"],
        "participants": [delegation["agent_id"]],
        "salt": uuid.uuid4().hex[:8],
        "payload_hash": compute_sha256_digest(delegation),
        "hash_algorithm": "SHA-256",
        "event_body_or_digest": {"delegation_id": delegation["delegation_id"]},
        "signer_id": "delegation_service",
        "signature_algorithm": "Ed25519",
    }
    # 签发真实 Ed25519 签名，替代 placeholder
    event["signature"] = issuer.sign_attestation(event)
    await submit_attestation(event)


@app.get("/v1/delegations/{delegation_id}")
async def api_get_delegation(delegation_id: str):
    """获取 IAC 记录。"""
    return await get_delegation(delegation_id)


@app.get("/v1/delegations/{delegation_id}/status")
async def api_get_delegation_status(delegation_id: str):
    """获取 IAC 状态。"""
    status = await get_delegation_status(delegation_id)
    return {"delegation_id": delegation_id, "status": status}


@app.post("/v1/delegations/{delegation_id}/suspend")
async def api_suspend_delegation(delegation_id: str, req: StatusChangeRequest = StatusChangeRequest()):
    """暂停 IAC。"""
    result = await suspend_delegation(delegation_id, req.reason)
    return result


@app.post("/v1/delegations/{delegation_id}/resume")
async def api_resume_delegation(delegation_id: str, req: StatusChangeRequest = StatusChangeRequest()):
    """恢复 IAC。"""
    result = await resume_delegation(delegation_id, req.reason)
    return result


@app.post("/v1/delegations/{delegation_id}/revoke")
async def api_revoke_delegation(delegation_id: str, req: StatusChangeRequest = StatusChangeRequest()):
    """吊销 IAC。"""
    result = await revoke_delegation(delegation_id, req.reason)
    return result


# ============================================================
# 公钥端点（供 PSP 验证 IAC Ed25519 签名）
# ============================================================
@app.get("/v1/public-key")
async def api_get_public_key():
    """返回 IAC 签发者的 Ed25519 公钥（PEM 格式）。

    PSP 在验证 IAC 时，需用此公钥校验 IAC 载荷中的 proof 字段，
    确保 IAC 确由委托授权服务签发、未被篡改。
    """
    issuer = get_issuer()
    return {"public_key": issuer.public_key_pem, "algorithm": "Ed25519"}


# ============================================================
# 健康检查
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "delegation_service"}


# ============================================================
# Demo 初始化
# ============================================================
async def run_demo_init():
    """执行 Demo 初始化：创建所有参与方身份和绑定。"""
    await init_db()

    # 等待数据库就绪
    await asyncio.sleep(0.1)

    results = []

    # 1. 创建买方智能体身份
    buyer = await create_credential(
        "urn:demo:agent:buyer:001", service_endpoint="http://127.0.0.1:58000"
    )
    results.append(("buyer_identity", buyer))

    # 2. 创建卖方智能体身份
    seller = await create_credential(
        "urn:demo:agent:seller:research-service-001",
        service_endpoint="http://127.0.0.1:8001",
    )
    results.append(("seller_identity", seller))

    # 3. 创建 DemoPSP 身份
    psp = await create_credential(
        "urn:demo:psp:local:v1", service_endpoint="http://127.0.0.1:8002"
    )
    results.append(("psp_identity", psp))

    # 4. 创建 DemoTrustService 身份
    trust = await create_credential(
        "urn:demo:trust-service:local:v1", service_endpoint="http://127.0.0.1:8003"
    )
    results.append(("trust_identity", trust))

    # 5. 创建委托人-买方智能体绑定
    uab = await create_user_agent_binding(
        user_agent_binding_id="uab_demo_001",
        delegator_id="delegator_demo_001",
        buyer_agent_id="urn:demo:agent:buyer:001",
    )
    results.append(("user_agent_binding", uab))

    # 6. 创建支付绑定
    pb = await create_payment_binding(
        payment_binding_id="paybind_buyer_001",
        user_agent_binding_id="uab_demo_001",
        buyer_agent_id="urn:demo:agent:buyer:001",
        payment_method_id="urn:demo:payment:local-balance:v1",
        sub_account_id="subacct_buyer_001",
    )
    results.append(("payment_binding", pb))

    return results


if __name__ == "__main__":
    import uvicorn

    asyncio.run(run_demo_init())
    uvicorn.run(app, host="127.0.0.1", port=8000)
