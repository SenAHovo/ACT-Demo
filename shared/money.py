"""
金额工具模块

统一使用 Decimal 进行金额运算，禁止使用 float。
所有金额输出统一为两位小数，币种必须显式声明。
"""

from decimal import Decimal, ROUND_HALF_UP

# 允许的币种
VALID_CURRENCIES = {"CNY", "USD", "EUR"}

# 金额精度：两位小数
QUANTIZE_FORMAT = Decimal("0.01")


def parse_amount(value: str | float | Decimal) -> Decimal:
    """将输入解析为 Decimal 金额，统一两位小数。"""
    if isinstance(value, float):
        raise TypeError("禁止使用 float 类型表示金额，请使用 str 或 Decimal")
    d = Decimal(str(value))
    return d.quantize(QUANTIZE_FORMAT, rounding=ROUND_HALF_UP)


def validate_currency(currency: str) -> str:
    """校验币种，返回大写形式。"""
    upper = currency.upper()
    if upper not in VALID_CURRENCIES:
        raise ValueError(f"不支持的币种: {currency}，允许的币种: {VALID_CURRENCIES}")
    return upper


def assert_amount_not_exceed(amount: Decimal, limit: Decimal, label: str = "") -> None:
    """断言金额不超过限额，否则抛出 ValueError。"""
    if amount > limit:
        msg = f"金额超限: {amount} > {limit}"
        if label:
            msg = f"[{label}] {msg}"
        raise ValueError(msg)
