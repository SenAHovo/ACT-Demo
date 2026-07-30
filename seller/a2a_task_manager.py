"""
类 A2A Task Manager — 任务生命周期管理

管理买家智能体在卖家智能体上创建的任务的完整生命周期（案例内部协议）：
  CREATED → PROCESSING → PAYMENT_REQUIRED → PAID → FULFILLED / FAILED
"""

from __future__ import annotations

import json
import uuid

from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError
from .database import get_db


VALID_TRANSITIONS: dict[str, list[str]] = {
    "CREATED": ["PROCESSING", "FAILED"],
    "PROCESSING": ["PAYMENT_REQUIRED", "FULFILLED", "FAILED"],
    "PAYMENT_REQUIRED": ["PAID", "FAILED"],
    "PAID": ["PROCESSING", "FULFILLED", "FAILED"],
    "FULFILLED": [],
    "FAILED": [],
}

STATUS_RANK = {"CREATED": 0, "PROCESSING": 1, "PAYMENT_REQUIRED": 2, "PAID": 3, "FULFILLED": 4, "FAILED": -1}


async def create_task(
    buyer_agent_id: str,
    goal: str,
    delegation_id: str = "",
) -> dict:
    """创建任务。买家在卖家上发起一个新任务。"""
    task_id = f"a2a_task_{uuid.uuid4().hex[:16]}"
    now_iso = to_iso(utc_now())

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO a2a_tasks (task_id, buyer_agent_id, delegation_id, goal, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'CREATED', ?, ?)""",
            (task_id, buyer_agent_id, delegation_id, goal, now_iso, now_iso),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "task_id": task_id,
        "buyer_agent_id": buyer_agent_id,
        "delegation_id": delegation_id,
        "goal": goal,
        "status": "CREATED",
        "created_at": now_iso,
    }


async def get_task(task_id: str) -> dict:
    """获取 Task 详情。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM a2a_tasks WHERE task_id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.SERVICE_NOT_FOUND, f"任务不存在: {task_id}")
        return dict(row)
    finally:
        await db.close()


async def update_task_status(task_id: str, new_status: str) -> dict:
    """更新 Task 状态（带合法转换校验）。"""
    current = await get_task(task_id)
    old_status = current["status"]

    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            f"任务状态不可从 {old_status} 转换到 {new_status}（允许: {allowed}）",
        )

    now_iso = to_iso(utc_now())
    db = await get_db()
    try:
        await db.execute(
            "UPDATE a2a_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (new_status, now_iso, task_id),
        )
        await db.commit()
    finally:
        await db.close()

    return {**current, "status": new_status, "updated_at": now_iso}


async def get_task_artifacts(task_id: str) -> list[dict]:
    """获取 Task 的所有产出物（Artifacts）。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            try:
                r["payload"] = json.loads(r.get("payload", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass
            results.append(r)
        return results
    finally:
        await db.close()


async def get_task_messages(task_id: str) -> list[dict]:
    """获取 Task 的所有消息。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM a2a_messages WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
