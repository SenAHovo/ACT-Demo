"""Artifact 存储 — 保存从卖方获取的交付物。"""
import json
from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest
from .database import get_db

async def save_artifact(artifact: dict, service_id: str, trade_no: str) -> None:
    db = await get_db()
    try:
        payload = artifact.get("payload", {})
        await db.execute(
            """INSERT INTO artifacts
               (artifact_id, artifact_type, service_id, trade_no, content_digest, payload, source_artifact_ids, retrieved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact.get("artifact_id", ""),
                artifact.get("artifact_type", ""),
                service_id,
                trade_no,
                compute_sha256_digest(payload),
                json.dumps(payload),
                json.dumps(artifact.get("source_artifact_ids", [])),
                to_iso(utc_now()),
            ),
        )
        await db.commit()
    finally:
        await db.close()
