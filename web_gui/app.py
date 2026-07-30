"""
Web GUI 服务 — FastAPI 应用

提供：
  - /               — HTML 页面
  - /api/chat/stream — SSE 流式对话
  - /api/services    — 服务目录
  - /api/files       — 文件管理 CRUD
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv; load_dotenv()

from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from buyer.conversation_agent import ConversationAgent
from shared.file_storage import list_files, get_file, get_file_content, get_file_text, save_upload, delete_file

import httpx

# ---- 全局 agent 实例 ----
_agent: ConversationAgent | None = None

# 数据库文件列表（用于重置）
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_FILES = ["buyer.db", "seller.db", "trust_service.db", "demo_psp.db", "delegation_service.db"]

app = FastAPI(title="ACT 智能体交易 Demo")

# 静态文件
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.on_event("startup")
async def startup_init_agent():
    """服务启动时预初始化智能体，避免首次 SSE 请求因 DB 初始化延迟而断开。"""
    global _agent
    if _agent is None:
        _agent = ConversationAgent()
        await _agent.initialize()


async def create_agent() -> ConversationAgent:
    """获取全局智能体实例（已在 startup 中初始化）。"""
    global _agent
    if _agent is None:
        # 兜底：仅当 startup 未执行时
        _agent = ConversationAgent()
        await _agent.initialize()
    return _agent


# ============================================================
# 页面
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================
# 对话 SSE
# ============================================================
@app.get("/api/chat/stream")
async def chat_stream(message: str = Query(...), file_ids: str = Query("")):
    agent = await create_agent()

    # 解析 file_ids 参数: "f1,f2" → ["f1", "f2"]
    parsed_file_ids = [fid.strip() for fid in file_ids.split(",") if fid.strip()] if file_ids else None

    async def generate():
        try:
            async for sse in agent.chat_stream(message, file_ids=parsed_file_ids):
                yield sse
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'text': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# 服务目录
# ============================================================
@app.get("/api/services")
async def services_list():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 通过服务目录获取（含价格、service_id）
            resp = await client.get("http://127.0.0.1:8001/v1/catalog")
            if resp.status_code == 200:
                return {"services": resp.json()}
    except Exception:
        pass
    return {"services": []}


# ============================================================
# 文件管理 API
# ============================================================
@app.get("/api/files")
async def files_list(source: str | None = None, tag: str | None = None):
    files = list_files(source=source, tag=tag)
    return {"files": files}


@app.get("/api/files/{file_id}")
async def file_info(file_id: str):
    entry = get_file(file_id)
    if not entry:
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    return entry


@app.get("/api/files/{file_id}/download")
async def file_download(file_id: str):
    entry = get_file(file_id)
    if not entry:
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    content = get_file_content(file_id)
    if content is None:
        return JSONResponse({"error": "文件内容为空"}, status_code=404)
    from fastapi.responses import Response
    from urllib.parse import quote
    filename = entry["filename"]
    encoded = quote(filename, safe='')
    return Response(
        content=content,
        media_type=entry.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@app.get("/api/files/{file_id}/content")
async def file_content(file_id: str):
    text = get_file_text(file_id)
    if text is None:
        return JSONResponse({"error": "无法读取文件内容"}, status_code=404)
    return {"content": text, "file_id": file_id}


@app.post("/api/files/upload")
async def file_upload(file: UploadFile = File(...)):
    data = await file.read()
    entry = save_upload(data, file.filename or "unknown")
    return entry


@app.delete("/api/files/{file_id}")
async def file_delete(file_id: str):
    ok = delete_file(file_id)
    if not ok:
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    return {"ok": True}


@app.post("/api/reset")
async def reset_system():
    """重置全部数据库和智能体记忆。"""
    global _agent

    deleted = []
    errors = []
    data_dir = _DATA_DIR

    # 1. 删除所有数据库文件
    for db_file in _DB_FILES:
        db_path = os.path.join(data_dir, db_file)
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        for p in [wal_path, shm_path, db_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    deleted.append(os.path.basename(p))
                except Exception as e:
                    errors.append(f"删除 {os.path.basename(p)} 失败: {e}")

    # 2. 清理 PSP 内存中的交易凭证（trade_store）
    try:
        from demo_psp.trade_store import reset_store
        reset_store()
    except Exception as e:
        errors.append(f"PSP 内存存储清理失败: {e}")

    # 3. 重新初始化 seller 数据库（含种子数据）
    try:
        from seller.database import init_db as seller_init_db
        from seller.catalog import seed_catalog
        await seller_init_db()
        await seed_catalog()
    except Exception as e:
        errors.append(f"卖家数据库初始化失败: {e}")

    # 4. 重新初始化 buyer 数据库并重建智能体实例（清空对话记忆）
    try:
        _agent = ConversationAgent()
        await _agent.initialize()
    except Exception as e:
        errors.append(f"买家智能体初始化失败: {e}")

    # 5. 重新初始化 PSP（子账户、签名密钥）
    try:
        from demo_psp.app import run_demo_init
        await run_demo_init()
    except Exception as e:
        errors.append(f"PSP 初始化失败: {e}")

    # 6. 重新初始化委托服务（身份、绑定）
    try:
        from delegation_service.app import run_demo_init as delegation_init
        await delegation_init()
    except Exception as e:
        errors.append(f"委托服务初始化失败: {e}")

    return {
        "ok": len(errors) == 0,
        "deleted_files": deleted,
        "errors": errors,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# 委托授权确认
# ============================================================
@app.post("/api/delegation/confirm")
async def delegation_confirm():
    global _agent
    if _agent:
        _agent.confirm_delegation()
    return {"ok": True}


@app.post("/api/delegation/cancel")
async def delegation_cancel():
    global _agent
    if _agent:
        _agent.cancel_delegation()
    return {"ok": True}


# ============================================================
# 账户充值
# ============================================================
@app.post("/api/account/topup")
async def account_topup():
    """给买方账户充值 10 CNY。"""
    import httpx
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post("http://127.0.0.1:8002/v1/subaccounts/subacct_buyer_001/topup?amount=10.0")
        if resp.status_code == 200:
            return resp.json()
        return JSONResponse({"error": "PSP 充值失败"}, status_code=502)
