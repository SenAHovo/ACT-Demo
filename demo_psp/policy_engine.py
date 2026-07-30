"""
策略引擎模块

核验单笔金额、累计金额、卖方、服务类别、支付方法。
"""

from __future__ import annotations

from decimal import Decimal
import json

from shared.money import parse_amount, assert_amount_not_exceed
from shared.errors import ErrorCode, AppError


def check_single_limit(amount: Decimal, max_single: Decimal) -> None:
    """检查单笔限额。"""
    assert_amount_not_exceed(amount, max_single, "单笔限额")


def check_total_limit(
    amount: Decimal,
    total_spent: Decimal,
    max_total: Decimal,
) -> None:
    """检查累计限额。"""
    new_total = total_spent + amount
    assert_amount_not_exceed(new_total, max_total, "累计限额")


def check_seller_allowed(seller_id: str, allowed_sellers: list[str]) -> None:
    """检查卖方是否在允许列表中。"""
    if allowed_sellers and seller_id not in allowed_sellers:
        raise AppError(ErrorCode.SELLER_NOT_ALLOWED, f"卖方不允许: {seller_id}")


def check_category_allowed(category: str, allowed_categories: list[str]) -> None:
    """检查服务类别是否在允许列表中。"""
    if allowed_categories and category not in allowed_categories:
        raise AppError(ErrorCode.CATEGORY_NOT_ALLOWED, f"类别不允许: {category}")


def check_method_allowed(method_id: str, allowed_methods: list[str]) -> None:
    """检查支付方法是否在允许列表中。"""
    if allowed_methods and method_id not in allowed_methods:
        raise AppError(ErrorCode.METHOD_NOT_ALLOWED, f"支付方法不允许: {method_id}")


def parse_decimal_list_from_iac(iac: dict, field: str) -> list[str]:
    """从 IAC 字典中解析 JSON 字符串列表字段。"""
    raw = iac.get(field, "[]")
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return []
