"""
交互适配器模块

校验 InteractionEnvelope，管理会话/任务/消息。
"""

from __future__ import annotations

from shared.errors import ErrorCode, AppError
from .database import get_db
from shared.time_utils import utc_now, to_iso


async def validate_envelope(envelope: dict) -> dict:
    """校验交互信封，管理会话和消息序列。"""
    session_id = envelope.get("session_id")
    task_id = envelope.get("task_id")
    message_id = envelope.get("message_id")

    if not all([session_id, task_id, message_id]):
        raise AppError(ErrorCode.INVALID_INTERACTION_ENVELOPE, "缺少必须字段")

    db = await get_db()
    try:
        now_iso = to_iso(utc_now())

        # 确保会话存在
        await db.execute(
            """INSERT OR IGNORE INTO sessions (session_id, buyer_agent_id, created_at, state)
               VALUES (?, ?, ?, 'ACTIVE')""",
            (session_id, envelope.get("sender_id", "unknown"), now_iso),
        )

        # 确保任务存在
        await db.execute(
            """INSERT OR IGNORE INTO service_tasks (task_id, session_id, state, created_at)
               VALUES (?, ?, 'SUBMITTED', ?)""",
            (task_id, session_id, now_iso),
        )

        # 消息去重
        cursor = await db.execute(
            "SELECT message_id FROM service_messages WHERE message_id = ?",
            (message_id,),
        )
        if await cursor.fetchone():
            raise AppError(ErrorCode.MESSAGE_REPLAYED, f"消息已处理: {message_id}")

        # 记录消息
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM service_messages WHERE task_id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        seq = (row["cnt"] if row else 0) + 1

        await db.execute(
            """INSERT INTO service_messages (message_id, task_id, session_id, sequence, received_at)
               VALUES (?, ?, ?, ?, ?)""",
            (message_id, task_id, session_id, seq, now_iso),
        )
        await db.commit()

        return envelope
    finally:
        await db.close()
