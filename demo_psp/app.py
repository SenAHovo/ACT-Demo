"""
DemoPSP — FastAPI 应用入口

运行端口: 8002
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.errors import AppError, ErrorCode
from shared.signatures import generate_keypair, public_key_to_pem
from .database import init_db
from .payment_processor import process_payment, set_signing_key
from .proof_service import verify_proof, get_proof
from .account_service import get_account, create_sub_account, topup_account
from .attestation_outbox import enqueue_attestation, flush_outbox


@asynccontextmanager
async def lifespan(app: FastAPI):
    """后台定期提交存证出箱。"""
    async def _flush_loop():
        while True:
            await asyncio.sleep(30)
            try:
                results = await flush_outbox()
                if results:
                    submitted = sum(1 for r in results if r["success"])
                    print(f"[PSP 存证] 提交 {submitted}/{len(results)} 条记录")
            except Exception as e:
                print(f"[PSP 存证] 提交异常: {e}")

    task = asyncio.create_task(_flush_loop())
    yield
    task.cancel()


app = FastAPI(title="Demo PSP", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    status = 400
    if "EXCEEDED" in exc.code.value or "INSUFFICIENT" in exc.code.value:
        status = 402
    elif "NOT_FOUND" in exc.code.value:
        status = 404
    return JSONResponse(status_code=status, content={"error": exc.code.value, "message": exc.message})


# ============================================================
# 请求模型
# ============================================================
class PaymentRequest(BaseModel):
    request_id: str
    request_timestamp: str | None = None
    session_id: str = ""
    task_id: str = ""
    delegation_id: str
    user_agent_binding_id: str
    payment_binding_id: str
    agent_credential_ref: str
    iac: dict = {}
    sub_account_id: str
    out_trade_no: str = ""
    resource_id: str
    resource_digest: str = ""
    service_id: str
    service_category: str
    seller_id: str
    buyer_agent_id: str
    amount: str
    currency: str = "CNY"
    method_id: str = ""
    signature: str = ""


class VerifyProofRequest(BaseModel):
    trade_no: str
    resource_id: str = ""
    seller_id: str = ""
    buyer_agent_id: str = ""
    amount: str = ""
    session_id: str = ""
    task_id: str = ""


class FulfillmentRequest(BaseModel):
    trade_no: str


# ============================================================
# Schema 端点
# ============================================================
@app.get("/schemas/local-balance-v1.json")
async def payment_schema():
    return {
        "method_id": "urn:demo:payment:local-balance:v1",
        "name": "本地模拟余额支付",
        "currency": "CNY",
        "description": "教学用途，不处理真实资金",
    }


# ============================================================
# 账户端点
# ============================================================
@app.get("/v1/subaccounts/{sub_account_id}")
async def api_get_account(sub_account_id: str):
    return await get_account(sub_account_id)


@app.post("/v1/subaccounts/{sub_account_id}/topup")
async def api_topup_account(sub_account_id: str, amount: float = 10.0):
    """充值指定金额到子账户。"""
    return await topup_account(sub_account_id, str(amount))


# ============================================================
# 支付端点
# ============================================================
@app.post("/v1/payments")
async def api_create_payment(req: PaymentRequest):
    result = await process_payment(req.model_dump())

    # 异步提交存证（含完整上下文）
    import asyncio
    asyncio.create_task(_submit_payment_event(req, result))

    return result


async def _submit_payment_event(req: PaymentRequest, result: dict):
    """构建完整的支付存证事件，包含所有链路关联字段。"""
    trade_no = result.get("trade_no", "")
    proof = result.get("proof", {})

    await enqueue_attestation(
        event_type="act:payment:transaction-completed",
        payload={
            "trade_no": trade_no,
            "out_trade_no": req.out_trade_no,
            "delegation_id": req.delegation_id,
            "session_id": req.session_id,
            "task_id": req.task_id,
            "resource_id": req.resource_id,
            "service_id": req.service_id,
            "seller_id": req.seller_id,
            "buyer_agent_id": req.buyer_agent_id,
            "amount": req.amount,
            "currency": req.currency,
            "new_balance": result.get("new_balance", ""),
        },
        delegation_id=req.delegation_id,
        task_id=req.task_id,
        trade_no=trade_no,
        out_trade_no=req.out_trade_no,
        participants=[req.buyer_agent_id, req.seller_id, "urn:demo:psp:local:v1"],
    )


@app.get("/v1/payments/{out_trade_no}")
async def api_query_payment(out_trade_no: str):
    from .adapters.local_balance import LocalBalanceAdapter
    adapter = LocalBalanceAdapter()
    result = await adapter.query(out_trade_no)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "PAYMENT_NOT_FOUND", "message": f"交易不存在: {out_trade_no}"})
    return result


# ============================================================
# 凭证端点
# ============================================================
@app.post("/v1/payment-proofs/verify")
async def api_verify_proof(req: VerifyProofRequest):
    result = await verify_proof(req.model_dump())
    return result


@app.post("/v1/trades/{trade_no}/fulfillment")
async def api_notify_fulfillment(trade_no: str, req: FulfillmentRequest = FulfillmentRequest(trade_no="")):
    from .adapters.local_balance import LocalBalanceAdapter
    from .database import get_db

    actual_trade_no = trade_no or req.trade_no

    adapter = LocalBalanceAdapter()
    await adapter.notify_fulfillment(actual_trade_no)

    # 查找支付记录以获取存证上下文
    delegation_id, task_id, out_trade_no, buyer_id, seller_id = "", "", "", "", ""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT delegation_id, task_id, out_trade_no, buyer_agent_id, seller_id FROM payments WHERE trade_no = ?",
            (actual_trade_no,),
        )
        row = await cursor.fetchone()
        if row:
            delegation_id = row["delegation_id"] or ""
            task_id = row["task_id"] or ""
            out_trade_no = row["out_trade_no"] or ""
            buyer_id = row["buyer_agent_id"] or ""
            seller_id = row["seller_id"] or ""
    finally:
        await db.close()

    # 异步提交存证（含完整上下文）
    import asyncio
    asyncio.create_task(enqueue_attestation(
        event_type="demo:payment:proof-verified",
        payload={
            "trade_no": actual_trade_no,
            "out_trade_no": out_trade_no,
            "delegation_id": delegation_id,
            "task_id": task_id,
        },
        delegation_id=delegation_id,
        task_id=task_id,
        trade_no=actual_trade_no,
        out_trade_no=out_trade_no,
        participants=[buyer_id, seller_id, "urn:demo:psp:local:v1"],
    ))

    return {"status": "OK", "trade_no": actual_trade_no}


# ============================================================
# 健康检查
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "demo_psp"}


# ============================================================
# Demo 初始化
# ============================================================
async def run_demo_init():
    """初始化 PSP：创建数据库表、模拟子账户、设置签名密钥。"""
    await init_db()

    # 生成 PSP 签名密钥
    priv, pub = generate_keypair()
    set_signing_key(priv)

    # 创建默认子账户
    await create_sub_account(
        sub_account_id="subacct_buyer_001",
        buyer_agent_id="urn:demo:agent:buyer:001",
        payment_binding_id="paybind_buyer_001",
        initial_balance="5.00",
    )

    return {
        "psp_id": "urn:demo:psp:local:v1",
        "public_key": public_key_to_pem(pub),
        "sub_accounts": ["subacct_buyer_001"],
    }
