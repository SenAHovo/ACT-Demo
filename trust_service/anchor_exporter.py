"""
锚点导出模块

生成待锚定摘要（教学用途，不实际写入链上）。
"""

import uuid
from shared.time_utils import utc_now, to_iso
from shared.signatures import compute_sha256_digest


def export_anchor(attestation_ids: list[str]) -> dict:
    """生成待锚定摘要，返回 Merkle 根（简化版用哈希链代替）。"""
    now = utc_now()
    # 将所有 attestation ID 串联后取 SHA-256 作为锚定摘要
    concatenated = "|".join(sorted(attestation_ids))
    anchor_digest = compute_sha256_digest({"ids": concatenated})

    return {
        "anchor_id": f"anchor_{uuid.uuid4().hex[:16]}",
        "generated_at": to_iso(now),
        "attestation_count": len(attestation_ids),
        "anchor_digest": anchor_digest,
        "attestation_ids": attestation_ids,
        "note": "教学用途，未实际写入链上",
    }
