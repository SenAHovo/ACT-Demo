"""
证据包服务模块

按 trade_no 或 delegation_id 导出证据包。
"""

import json, uuid
from shared.time_utils import utc_now, to_iso
from .database import get_db
from .trace_service import get_trace


async def export_evidence(
    delegation_id: str = "",
    trade_no: str = "",
) -> dict:
    """导出证据包：收集所有相关存证记录打包返回。"""
    trace = await get_trace(delegation_id=delegation_id, trade_no=trade_no)

    package_id = f"pkg_{uuid.uuid4().hex[:16]}"
    now_iso = to_iso(utc_now())

    evidence = {
        "package_id": package_id,
        "created_at": now_iso,
        "delegation_id": delegation_id,
        "trade_no": trade_no,
        "events": trace["events"],
        "summary": {
            "total_events": trace["event_count"],
            "chain_complete": trace["chain_complete"],
        },
    }

    # 保存证据包索引
    db = await get_db()
    try:
        attestation_ids = [e["attestation_id"] for e in trace["events"]]
        await db.execute(
            "INSERT INTO evidence_packages (package_id, query_params, attestation_ids, created_at) VALUES (?, ?, ?, ?)",
            (
                package_id,
                json.dumps({"delegation_id": delegation_id, "trade_no": trade_no}),
                json.dumps(attestation_ids),
                now_iso,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return evidence
