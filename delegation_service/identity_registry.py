"""
身份注册表模块

维护买方智能体、卖方智能体、DemoPSP 和 DemoTrustService 的本地身份记录。
"""

from __future__ import annotations

import json

from .database import get_db
from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError


async def register_identity(
    agent_id: str,
    agent_id_scheme: str,
    credential_id: str,
    public_key: str,
    service_endpoint: str | None = None,
    expires_at: str | None = None,
) -> dict:
    """注册智能体身份记录。"""
    db = await get_db()
    try:
        now_iso = to_iso(utc_now())
        await db.execute(
            """INSERT OR IGNORE INTO agent_identities
               (agent_id, agent_id_scheme, credential_id, public_key,
                credential_status, service_endpoint, issued_at, expires_at)
               VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?)""",
            (agent_id, agent_id_scheme, credential_id, public_key,
             service_endpoint, now_iso, expires_at),
        )
        await db.commit()
        return await _get_identity_dict(db, agent_id)
    finally:
        await db.close()


async def get_identity(agent_id: str) -> dict:
    """获取智能体身份记录。"""
    db = await get_db()
    try:
        return await _get_identity_dict(db, agent_id)
    finally:
        await db.close()


async def _get_identity_dict(db, agent_id: str) -> dict:
    cursor = await db.execute(
        "SELECT * FROM agent_identities WHERE agent_id = ?", (agent_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise AppError(ErrorCode.IDENTITY_NOT_FOUND, f"身份未找到: {agent_id}")
    return dict(row)


async def update_credential_status(
    credential_id: str, new_status: str, reason: str = ""
) -> None:
    """更新凭证状态并记录历史。"""
    db = await get_db()
    try:
        now_iso = to_iso(utc_now())
        # 查当前状态
        cursor = await db.execute(
            "SELECT credential_status FROM agent_identities WHERE credential_id = ?",
            (credential_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.IDENTITY_NOT_FOUND, f"凭证未找到: {credential_id}")
        old_status = row["credential_status"]

        # 更新状态
        await db.execute(
            "UPDATE agent_identities SET credential_status = ? WHERE credential_id = ?",
            (new_status, credential_id),
        )
        # 写历史
        await db.execute(
            """INSERT INTO credential_status_history
               (credential_id, old_status, new_status, changed_at, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (credential_id, old_status, new_status, now_iso, reason),
        )
        await db.commit()
    finally:
        await db.close()


async def list_identities() -> list[dict]:
    """列出所有身份记录。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM agent_identities")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_credential_status(credential_id: str) -> dict:
    """获取凭证状态及归属信息。

    Returns:
        {"credential_id": ..., "status": ..., "agent_id": ...}
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT credential_status, agent_id FROM agent_identities WHERE credential_id = ?",
            (credential_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.IDENTITY_NOT_FOUND, f"凭证未找到: {credential_id}")
        return {
            "credential_id": credential_id,
            "status": row["credential_status"],
            "agent_id": row["agent_id"],
        }
    finally:
        await db.close()
