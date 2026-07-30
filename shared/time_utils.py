"""
时间工具模块

统一使用 ISO 8601 UTC 格式处理所有时间。
"""

from datetime import datetime, timezone, timedelta


def utc_now() -> datetime:
    """返回当前 UTC 时间（带时区）。"""
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """将 datetime 格式化为 ISO 8601 UTC 字符串。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def from_iso(s: str) -> datetime:
    """从 ISO 8601 字符串解析 datetime。"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_expired(expires_at: datetime) -> bool:
    """检查时间是否已过期。"""
    return utc_now() > expires_at


def minutes_from_now(minutes: int) -> datetime:
    """返回当前时间 + N 分钟后的 UTC 时间。"""
    return utc_now() + timedelta(minutes=minutes)
