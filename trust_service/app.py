"""
信任服务 — FastAPI 应用入口

运行端口: 8003
"""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.errors import AppError
from .database import init_db
from .record_index import store_attestation, get_attestation, list_attestations
from .verifier import verify_attestation
from .trace_service import get_trace
from .evidence_service import export_evidence
from .anchor_exporter import export_anchor

app = FastAPI(title="Demo Trust Service", version="1.0.0")


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    return JSONResponse(
        status_code=400,
        content={"error": exc.code.value, "message": exc.message},
    )


# ============================================================
# 存证
# ============================================================
class AttestationRequest(BaseModel):
    attestation_id: str = ""
    event_type: str
    event_time: str = ""
    intent_id: str | None = None
    delegation_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    out_trade_no: str | None = None
    trade_no: str | None = None
    upstream_attestation_ids: list[str] = []
    participants: list[str] = []
    payload_hash: str
    hash_algorithm: str = "SHA-256"
    event_body_or_digest: dict | str | None = None
    signer_id: str = ""
    signature: str = ""
    source_record_ref: str | None = None


@app.post("/v1/attestations")
async def api_store_attestation(req: AttestationRequest):
    return await store_attestation(req.model_dump())


@app.get("/v1/attestations/{attestation_id}")
async def api_get_attestation(attestation_id: str):
    return await get_attestation(attestation_id)


@app.get("/v1/attestations")
async def api_list_attestations(
    delegation_id: str = "",
    out_trade_no: str = "",
    event_type: str = "",
    limit: int = 100,
):
    return await list_attestations(
        delegation_id=delegation_id,
        out_trade_no=out_trade_no,
        event_type=event_type,
        limit=limit,
    )


# ============================================================
# 验证
# ============================================================
class VerifyRequest(BaseModel):
    attestation_id: str


@app.post("/v1/attestations/{attestation_id}/verify")
async def api_verify_attestation(attestation_id: str):
    return await verify_attestation(attestation_id)


# ============================================================
# 追踪
# ============================================================
@app.get("/v1/traces/{delegation_id}")
async def api_get_trace(delegation_id: str):
    return await get_trace(delegation_id=delegation_id)


# ============================================================
# 证据包
# ============================================================
class EvidenceRequest(BaseModel):
    delegation_id: str = ""
    trade_no: str = ""


@app.post("/v1/evidence-packages")
async def api_export_evidence(req: EvidenceRequest):
    return await export_evidence(
        delegation_id=req.delegation_id,
        trade_no=req.trade_no,
    )


# ============================================================
# 锚点
# ============================================================
class AnchorRequest(BaseModel):
    attestation_ids: list[str]


@app.post("/v1/anchors/export")
async def api_export_anchor(req: AnchorRequest):
    return export_anchor(req.attestation_ids)


# ============================================================
# 健康检查
# ============================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "trust_service"}


# ============================================================
# Demo 初始化
# ============================================================
async def run_demo_init():
    await init_db()
    return {"agent_id": "urn:demo:trust-service:local:v1", "status": "ready"}
