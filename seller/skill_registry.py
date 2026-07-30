"""
Skill 注册表模块

建立 skill_id → Handler 模块 → artifact_type 的映射。
"""

from __future__ import annotations

import importlib
from shared.errors import ErrorCode, AppError

SKILL_MAP = {
    "weekly-report-generation": {
        "handler": "seller.skills.weekly_report_generation",
        "artifact_type": "document_docx",
    },
    "travel-guide-generation": {
        "handler": "seller.skills.travel_guide_generation",
        "artifact_type": "document_docx",
    },
    "translation": {
        "handler": "seller.skills.translation",
        "artifact_type": "translation",
    },
}


async def execute_skill(skill_id: str, input_data: dict) -> dict:
    """根据 skill_id 执行对应 Skill。"""
    if skill_id not in SKILL_MAP:
        raise AppError(ErrorCode.SERVICE_NOT_FOUND, f"Skill 未注册: {skill_id}")

    cfg = SKILL_MAP[skill_id]
    handler = cfg["handler"]
    artifact_type = cfg["artifact_type"]

    try:
        module = importlib.import_module(handler)
        payload = module.run(input_data)

        return {
            "skill_id": skill_id,
            "artifact_type": artifact_type,
            "payload": payload,
            "source_artifact_ids": input_data.get("source_artifact_ids", []),
        }
    except ModuleNotFoundError:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            f"Skill 模块未找到: {handler}"
        )
    except Exception as e:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, f"Skill 执行失败: {e}")
