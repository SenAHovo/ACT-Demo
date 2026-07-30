"""
文件存储管理模块

提供文件的上传、存储、下载和列表功能。
用于服务交付物（报告、数据导出等）和用户上传文件的管理。
"""

from __future__ import annotations

import os
import json
import uuid
import shutil
from datetime import datetime, timezone
from typing import BinaryIO

# 文件存储根目录
STORAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "files"
)

# 元数据文件
META_FILE = os.path.join(STORAGE_ROOT, "_metadata.json")


def _ensure_storage():
    """确保存储目录和元数据文件存在。"""
    os.makedirs(STORAGE_ROOT, exist_ok=True)
    if not os.path.exists(META_FILE):
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load_meta() -> dict:
    """加载文件元数据。"""
    _ensure_storage()
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_meta(meta: dict):
    """保存文件元数据。"""
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def save_file(
    filename: str,
    content: str | bytes,
    *,
    description: str = "",
    tags: list[str] | None = None,
    source: str = "system",
) -> dict:
    """
    保存文件到存储系统。

    Args:
        filename: 显示名称
        content: 文件内容（文本或二进制）
        description: 文件描述
        tags: 标签列表
        source: 来源（"system" 服务生成 / "user" 用户上传）

    Returns:
        文件元数据字典，包含 file_id, path, url 等
    """
    _ensure_storage()
    
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    
    # 保留原始扩展名
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".txt"
    stored_name = f"{file_id}{ext}"
    stored_path = os.path.join(STORAGE_ROOT, stored_name)
    
    # 写入文件
    if isinstance(content, str):
        with open(stored_path, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
    else:
        with open(stored_path, "wb") as f:
            f.write(content)
        size = len(content)
    
    now = datetime.now(timezone.utc).isoformat()
    meta_entry = {
        "file_id": file_id,
        "filename": filename,
        "stored_name": stored_name,
        "path": stored_path,
        "size": size,
        "description": description,
        "tags": tags or [],
        "source": source,
        "created_at": now,
        "content_type": _guess_content_type(ext),
    }
    
    meta = _load_meta()
    meta[file_id] = meta_entry
    _save_meta(meta)
    
    return meta_entry


def get_file(file_id: str) -> dict | None:
    """获取文件元数据。"""
    meta = _load_meta()
    return meta.get(file_id)


def get_file_content(file_id: str) -> bytes | None:
    """读取文件内容。"""
    entry = get_file(file_id)
    if not entry:
        return None
    path = entry["path"]
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def get_file_text(file_id: str) -> str | None:
    """读取文本文件内容。"""
    content = get_file_content(file_id)
    if content is None:
        return None
    return content.decode("utf-8")


def list_files(source: str | None = None, tag: str | None = None) -> list[dict]:
    """列出文件，可按来源或标签筛选。"""
    meta = _load_meta()
    files = list(meta.values())
    if source:
        files = [f for f in files if f["source"] == source]
    if tag:
        files = [f for f in files if tag in f.get("tags", [])]
    files.sort(key=lambda f: f["created_at"], reverse=True)
    return files


def delete_file(file_id: str) -> bool:
    """删除文件及其元数据。"""
    meta = _load_meta()
    entry = meta.pop(file_id, None)
    if entry is None:
        return False
    _save_meta(meta)
    path = entry["path"]
    if os.path.exists(path):
        os.remove(path)
    return True


def save_service_result(
    service_id: str,
    artifact: dict,
    trade_no: str = "",
) -> dict | None:
    """
    将服务产出（artifact）保存为文件。

    Args:
        service_id: 服务 ID（如 doc.weekly.report）
        artifact: artifact 对象（含 payload）
        trade_no: 交易编号

    Returns:
        文件元数据，如果无法保存则返回 None
    """
    payload = artifact.get("payload", {})
    if not payload:
        return None

    tag = "service-output"
    
    if service_id == "utility.translation":
        # 翻译：文件模式（技能已自行保存），直接返回文件引用
        out_fid = payload.get("output_file_id")
        if out_fid:
            return {
                "file_id": out_fid,
                "filename": payload.get("output_filename", f"translation_{trade_no}.md"),
                "size": 0,
                "content_type": "text/markdown",
            }
        # 文本模式：保存为 JSON
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        filename = f"translation_{trade_no}.json"
        description = "翻译结果"
        
    elif service_id in ("doc.weekly.report", "lifestyle.travel.guide"):
        # 周报/攻略：技能已自行保存 MD，直接返回文件引用
        out_fid = payload.get("output_file_id")
        if out_fid:
            return {
                "file_id": out_fid,
                "filename": payload.get("output_filename", f"output_{trade_no}.md"),
                "size": 0,
                "content_type": "text/markdown",
            }
        return None
        
    else:
        return None

    return save_file(
        filename=filename,
        content=content,
        description=description,
        tags=[tag, service_id],
        source="system",
    )


def save_upload(file_data: bytes, filename: str) -> dict:
    """保存用户上传的文件。"""
    return save_file(
        filename=filename,
        content=file_data,
        description=f"用户上传: {filename}",
        tags=["user-upload"],
        source="user",
    )


def _guess_content_type(ext: str) -> str:
    """根据扩展名猜测 MIME 类型。"""
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return mapping.get(ext.lower(), "application/octet-stream")
