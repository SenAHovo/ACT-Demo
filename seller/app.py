"""
卖方智能体 — FastAPI 应用入口

运行端口: 8001
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.errors import AppError
from .database import init_db
from .catalog import get_all_services, get_service, seed_catalog
from .agent_card_serializer import get_agent_card
from .gbz_description_serializer import get_gbz_description
from .payment_adapter import get_payment_capability
from .authentication_adapter import verify_buyer_authentication
from .interaction_adapter import validate_envelope
from .commerce_controller import handle_service_invocation, get_order_status
from .attestation_outbox import enqueue_attestation, flush_outbox
from .a2a_task_manager import create_task, get_task as get_a2a_task, get_task_artifacts, get_task_messages
from .a2a_message_handler import handle_task_message, execute_service_after_payment


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
                    print(f"[卖家 存证] 提交 {submitted}/{len(results)} 条记录")
            except Exception as e:
                print(f"[卖家 存证] 提交异常: {e}")

    task = asyncio.create_task(_flush_loop())
    yield
    task.cancel()


app = FastAPI(title="Seller Agent", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    status = 400
    code = exc.code.value
    if "NOT_FOUND" in code:
        status = 404
    elif "EXPIRED" in code or "INVALID" in code:
        status = 400
    elif "PAYMENT" in code:
        status = 402
    return JSONResponse(status_code=status, content={"error": code, "message": exc.message})


# ============================================================
# Agent Card / 描述
# ============================================================
@app.get("/.well-known/agent-card.json")
async def api_agent_card():
    return get_agent_card()


@app.get("/.well-known/agent-description.json")
async def api_agent_description():
    return get_gbz_description()


@app.get("/.well-known/act-payment-capability.json")
async def api_payment_capability():
    return get_payment_capability()


# ============================================================
# 服务目录
# ============================================================
@app.get("/v1/catalog")
async def api_catalog():
    return await get_all_services()


@app.get("/v1/catalog/{service_id}")
async def api_service_detail(service_id: str):
    return await get_service(service_id)


# ============================================================
# 认证
# ============================================================
class AuthRequest(BaseModel):
    assertion_id: str = ""


@app.post("/v1/sessions/authenticate")
async def api_authenticate(req: AuthRequest):
    return await verify_buyer_authentication(req.assertion_id)


# ============================================================
# 服务调用（核心）
# ============================================================
class ServiceInvokeRequest(BaseModel):
    service_id: str
    input: dict = {}
    delegation_id: str = ""
    payment_proof: dict | None = None


class WrappedInvokeRequest(BaseModel):
    """包含交互信封的服务调用。"""
    envelope: dict
    invocation: ServiceInvokeRequest


@app.post("/v1/services/{service_id}/invoke")
async def api_invoke_service(service_id: str, req: WrappedInvokeRequest):
    """服务调用入口 — 核心端点。"""
    # 校验信封
    await validate_envelope(req.envelope)

    # 构造调用
    invocation = req.invocation.model_dump()
    invocation["service_id"] = service_id

    result = await handle_service_invocation(invocation, req.envelope)

    # 如果是支付要求（HTTP 402），设置状态码
    if result.get("status") == "PAYMENT_REQUIRED":
        return JSONResponse(
            status_code=402,
            content=result,
            headers={"Payment-Needed": "true"},
        )

    # 履约完成，异步存证
    if result.get("status") == "FULFILLED":
        asyncio.create_task(enqueue_attestation(
            "act:commerce:fulfillment-completed",
            {"artifact_id": result.get("artifact", {}).get("artifact_id", "")},
            delegation_id=invocation.get("delegation_id", ""),
            task_id=result.get("artifact", {}).get("task_id", ""),
        ))

    return result


# ============================================================
# 任务 / 订单查询
# ============================================================
@app.get("/v1/tasks/{task_id}")
async def api_task_status(task_id: str):
    from .database import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM service_tasks WHERE task_id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "TASK_NOT_FOUND"})
        return dict(row)
    finally:
        await db.close()


@app.get("/v1/orders/{out_trade_no}")
async def api_order_status(out_trade_no: str):
    return await get_order_status(out_trade_no)


# ============================================================
# A2A 协议端点 — 商业交互域
# ============================================================
class A2ATaskRequest(BaseModel):
    buyer_agent_id: str
    goal: str
    delegation_id: str = ""


class A2AMessageRequest(BaseModel):
    sender_role: str  # "buyer_agent" | "seller_agent"
    content: str


class A2APaymentRequest(BaseModel):
    service_id: str
    skill_id: str
    input_data: dict = {}
    payment_proof: dict = {}
    trade_no: str = ""


@app.post("/v1/a2a/tasks")
async def api_a2a_create_task(req: A2ATaskRequest):
    """A2A: 创建任务。买家在卖家智能体上发起一个新任务。"""
    result = await create_task(
        buyer_agent_id=req.buyer_agent_id,
        goal=req.goal,
        delegation_id=req.delegation_id,
    )
    return result


@app.get("/v1/a2a/tasks/{task_id}")
async def api_a2a_get_task(task_id: str):
    """A2A: 查询任务状态。"""
    return await get_a2a_task(task_id)


@app.post("/v1/a2a/tasks/{task_id}/messages")
async def api_a2a_send_message(task_id: str, req: A2AMessageRequest):
    """A2A: 向任务发送消息。卖家智能体解析意图并调度 Skill。"""
    task = await get_a2a_task(task_id)

    result = await handle_task_message(
        task_id=task_id,
        sender_role=req.sender_role,
        content=req.content,
        delegation_id=task.get("delegation_id", ""),
    )

    # 履约完成，异步存证
    if result.get("result", {}).get("status") == "FULFILLED":
        artifact = result.get("result", {}).get("artifact", {})
        asyncio.create_task(enqueue_attestation(
            "act:commerce:fulfillment-completed",
            {"task_id": task_id, "artifact_id": artifact.get("artifact_id", "")},
            delegation_id=task.get("delegation_id", ""),
            task_id=task_id,
        ))

    return result


@app.get("/v1/a2a/tasks/{task_id}/messages")
async def api_a2a_get_messages(task_id: str):
    """A2A: 获取任务的所有消息。"""
    return await get_task_messages(task_id)


@app.get("/v1/a2a/tasks/{task_id}/artifacts")
async def api_a2a_get_artifacts(task_id: str):
    """A2A: 获取任务的产出物（Artifacts）。"""
    return await get_task_artifacts(task_id)


@app.post("/v1/a2a/tasks/{task_id}/pay")
async def api_a2a_execute_after_payment(task_id: str, req: A2APaymentRequest):
    """A2A: 支付完成后执行服务交付（买家完成 PSP 支付后回调）。"""
    result = await execute_service_after_payment(
        task_id=task_id,
        service_id=req.service_id,
        skill_id=req.skill_id,
        input_data=req.input_data,
        payment_proof=req.payment_proof,
        trade_no=req.trade_no,
    )

    # 存证
    if result.get("status") == "FULFILLED":
        artifact = result.get("artifact", {})
        task_info = await get_a2a_task(task_id)
        asyncio.create_task(enqueue_attestation(
            "act:commerce:fulfillment-completed",
            {"task_id": task_id, "artifact_id": artifact.get("artifact_id", "")},
            delegation_id=task_info.get("delegation_id", ""),
            task_id=task_id,
            trade_no=req.trade_no,
            participants=["urn:demo:agent:buyer:001", "urn:demo:agent:seller:research-service-001"],
        ))

    return result


# ============================================================
# 健康检查
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "seller"}


# ============================================================
# Demo 初始化
# ============================================================
async def run_demo_init():
    await init_db()
    await seed_catalog()
    return {"agent_id": "urn:demo:agent:seller:research-service-001", "services": 3}
