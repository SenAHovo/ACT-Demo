"""
追踪服务模块

按 delegation_id 或 trade_no 返回完整证据链。
"""

from .database import get_db


async def get_trace(delegation_id: str = "", trade_no: str = "") -> dict:
    """
    按 delegation_id 或 trade_no 检索完整证据链。

    返回:
        {
            "delegation_id": ...,
            "events": [...],  # 按时间排序的存证记录列表
            "event_count": N,
            "chain_complete": bool  # 简化判断：至少有 INTENT + PAYMENT + FULFILLMENT
        }
    """
    db = await get_db()
    try:
        conditions = []
        params: list = []
        if delegation_id:
            conditions.append("delegation_id = ?")
            params.append(delegation_id)
        if trade_no:
            conditions.append("trade_no = ?")
            params.append(trade_no)

        if not conditions:
            return {"delegation_id": delegation_id, "events": [], "event_count": 0, "chain_complete": False}

        where = " OR ".join(conditions)
        cursor = await db.execute(
            f"SELECT * FROM attestation_records WHERE {where} ORDER BY record_created_at",
            params,
        )
        rows = await cursor.fetchall()
        events = [dict(r) for r in rows]

        # 简化完整性判断
        event_types = {e["event_type"] for e in events}
        chain_complete = any(
            t in event_types
            for t in ["act:delegation:delegation-issued", "act:delegation:intent-created"]
        ) and "act:payment:transaction-completed" in event_types

        return {
            "delegation_id": delegation_id,
            "trade_no": trade_no,
            "events": events,
            "event_count": len(events),
            "chain_complete": chain_complete,
        }
    finally:
        await db.close()
