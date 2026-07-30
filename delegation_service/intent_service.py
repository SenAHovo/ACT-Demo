"""
意图服务模块

保存委托人确认后的 ISR（意图结构化记录），生成 intent_id。
"""

from __future__ import annotations

import uuid
import json

from decimal import Decimal

from shared.time_utils import utc_now, to_iso, minutes_from_now
from shared.money import parse_amount, validate_currency
from shared.identity import validate_agent_id, validate_agent_id_scheme
from shared.errors import ErrorCode, AppError
from .database import get_db
from .user_agent_binding import get_user_agent_binding


async def create_intent(
    task_goal: str,
    agent_id: str,
    agent_id_scheme: str,
    user_agent_binding_id: str,
    max_total_amount: str | Decimal,
    max_single_amount: str | Decimal,
    currency: str = "CNY",
    allowed_sellers: list[str] | None = None,
    allowed_categories: list[str] | None = None,
    allowed_payment_methods: list[str] | None = None,
    validity_minutes: int = 30,
    delegator_id: str = "",
) -> dict:
    """创建意图结构化记录（ISR）。

    在委托人确认后调用。
    """
    # 校验
    validate_agent_id(agent_id)
    validate_agent_id_scheme(agent_id_scheme)
    _currency = validate_currency(currency)
    _total = parse_amount(max_total_amount)
    _single = parse_amount(max_single_amount)

    if _single > _total:
        raise AppError(
            ErrorCode.SINGLE_LIMIT_EXCEEDED,
            f"单笔限额 {_single} 不能超过总预算 {_total}",
        )

    # 验证绑定
    binding = await get_user_agent_binding(user_agent_binding_id)
    if binding["buyer_agent_id"] != agent_id:
        raise AppError(
            ErrorCode.AGENT_ID_MISMATCH,
            f"绑定中的 agent_id 不匹配: {binding['buyer_agent_id']} vs {agent_id}",
        )

    sellers = allowed_sellers or []
    categories = allowed_categories or []
    methods = allowed_payment_methods or []

    intent_id = f"intent_{uuid.uuid4().hex[:16]}"
    now = utc_now()

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO intents
               (intent_id, task_goal, delegation_mode, validity_start_time,
                validity_end_time, max_total_amount, max_single_amount, currency,
                allowed_sellers, allowed_categories, allowed_payment_methods,
                agent_id, agent_id_scheme, user_agent_binding_id, confirmation_timestamp)
               VALUES (?, ?, 'BOUNDED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                intent_id,
                task_goal,
                to_iso(now),
                to_iso(minutes_from_now(validity_minutes)),
                str(_total),
                str(_single),
                _currency,
                json.dumps(sellers),
                json.dumps(categories),
                json.dumps(methods),
                agent_id,
                agent_id_scheme,
                user_agent_binding_id,
                to_iso(now),
            ),
        )
        await db.commit()

        row = await (await db.execute(
            "SELECT * FROM intents WHERE intent_id = ?", (intent_id,)
        )).fetchone()
        return dict(row)
    finally:
        await db.close()


async def get_intent(intent_id: str) -> dict:
    """获取意图记录。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM intents WHERE intent_id = ?", (intent_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise AppError(ErrorCode.INTENT_NOT_CONFIRMED, f"意图未找到: {intent_id}")
        return dict(row)
    finally:
        await db.close()
