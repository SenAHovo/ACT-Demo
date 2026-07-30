"""
服务目录模块

维护三项商品化服务及其价格。
"""

from __future__ import annotations

from decimal import Decimal
import json
from .database import get_db

SERVICES = [
    {
        "service_id": "doc.weekly.report",
        "skill_id": "weekly-report-generation",
        "name": "周报生成",
        "category": "document.office",
        "description": "上传模板文件（可选），描述工作内容和语言风格，生成专业的周报 MD 文档",
        "price": "0.30",
        "currency": "CNY",
    },
    {
        "service_id": "lifestyle.travel.guide",
        "skill_id": "travel-guide-generation",
        "name": "旅游攻略生成",
        "category": "lifestyle.travel",
        "description": "输入目的地、出发地和游玩天数，生成包含出行方式、景点、美食、文化和每日日程的旅游攻略 MD 文档",
        "price": "0.35",
        "currency": "CNY",
    },
    {
        "service_id": "utility.translation",
        "skill_id": "translation",
        "name": "多语言翻译",
        "category": "utility",
        "description": "支持文件翻译(DOCX/TXT/MD)和文本翻译，中英互译、中日、中韩等多语言，输出 MD 文件或文本",
        "price": "0.15",
        "currency": "CNY",
    },
]

SELLER_ID = "urn:demo:agent:seller:research-service-001"


async def seed_catalog() -> None:
    """初始化服务目录到数据库。"""
    db = await get_db()
    try:
        # 先清空旧数据
        await db.execute("DELETE FROM service_catalog")
        for svc in SERVICES:
            await db.execute(
                """INSERT INTO service_catalog
                   (service_id, skill_id, name, category, description, price, currency)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (svc["service_id"], svc["skill_id"], svc["name"],
                 svc["category"], svc["description"], svc["price"], svc["currency"]),
            )
        await db.commit()
    finally:
        await db.close()


async def get_all_services() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM service_catalog WHERE availability = 'ACTIVE'")
        rows = await cursor.fetchall()
        return [_format_service(dict(r)) for r in rows]
    finally:
        await db.close()


async def get_service(service_id: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM service_catalog WHERE service_id = ?", (service_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            from shared.errors import ErrorCode, AppError
            raise AppError(ErrorCode.SERVICE_NOT_FOUND, f"服务不存在: {service_id}")
        return _format_service(dict(row))
    finally:
        await db.close()


def _format_service(row: dict) -> dict:
    row["price"] = str(row["price"])
    row["seller_id"] = SELLER_ID
    row["seller_id_scheme"] = "demo"
    return row
