"""
智能体统一描述模块

维护 CanonicalAgentDescription，作为 A2A Agent Card 和 GB/Z 描述的统一事实源。
"""

from __future__ import annotations

from decimal import Decimal

AGENT_ID = "urn:demo:agent:seller:doc-service-001"
AGENT_ID_SCHEME = "demo"
AGENT_NAME = "文档与生活服务智能体"
AGENT_DESCRIPTION = "提供周报生成、旅游攻略生成和多语言翻译服务（教学用途）"


def get_canonical_description() -> dict:
    return {
        "agent_id": AGENT_ID,
        "agent_id_scheme": AGENT_ID_SCHEME,
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "version": "1.0.0",
        "capabilities": {
            "skills": [
                {
                    "skill_id": "weekly-report-generation",
                    "name": "周报生成",
                    "description": "上传 DOCX 模板，指定语言风格和工作内容，生成周报 DOCX",
                },
                {
                    "skill_id": "travel-guide-generation",
                    "name": "旅游攻略生成",
                    "description": "输入目的地、出发地、天数，生成综合旅游攻略 DOCX",
                },
                {
                    "skill_id": "translation",
                    "name": "多语言翻译",
                    "description": "支持文件翻译和文本翻译，中英/中日/中韩等多语言",
                },
            ],
            "payment": {
                "supported_methods": ["urn:demo:payment:local-balance:v1"],
                "psp_id": "urn:demo:psp:local:v1",
            },
        },
        "service_endpoint": "http://127.0.0.1:8001",
        "authentication": {
            "methods": ["demo_local_credential"],
        },
    }
