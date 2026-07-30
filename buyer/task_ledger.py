"""任务账本 — 记录子任务状态和支付流水。"""
from decimal import Decimal
from shared.time_utils import utc_now, to_iso
from .database import get_db

async def record_task(task_id: str, session_id: str, service_id: str, delegation_id: str, amount: str = "0") -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO task_ledger (task_id, session_id, delegation_id, service_id, amount, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""",
            (task_id, session_id, delegation_id, service_id, amount, to_iso(utc_now())),
        )
        await db.commit()
    finally:
        await db.close()

async def update_task(task_id: str, trade_no: str, amount: str, status: str = "COMPLETED") -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE task_ledger SET trade_no = ?, amount = ?, status = ?, completed_at = ? WHERE task_id = ?",
            (trade_no, amount, status, to_iso(utc_now()), task_id),
        )
        await db.commit()
    finally:
        await db.close()

async def get_total_spent(delegation_id: str, session_id: str) -> Decimal:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT SUM(CAST(amount AS DECIMAL)) as total FROM task_ledger WHERE delegation_id = ? AND session_id = ? AND status = 'COMPLETED'",
            (delegation_id, session_id),
        )
        row = await cursor.fetchone()
        total = Decimal(row["total"] or "0")
        return total.quantize(Decimal("0.01"))
    finally:
        await db.close()
