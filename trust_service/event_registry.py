"""
事件注册表

定义合法的 ACT 标准事件和 demo 命名空间事件类型。
"""

ACT_EVENTS = {
    "act:delegation:intent-created",
    "act:delegation:delegation-issued",
    "act:delegation:delegation-suspended",
    "act:delegation:delegation-resumed",
    "act:delegation:delegation-revoked",
    "act:delegation:delegation-expired",
    "act:commerce:decision-logged",
    "act:payment:transaction-completed",
    "act:commerce:fulfillment-completed",
}

DEMO_EVENTS = {
    "demo:identity:authenticated",
    "demo:payment:proof-verified",
    "demo:task:completed",
    "demo:attestation:submission-retried",
}

VALID_EVENTS = ACT_EVENTS | DEMO_EVENTS

ALLOWED_PATTERNS = ["act:", "demo:"]


def is_valid_event_type(event_type: str) -> bool:
    if event_type in VALID_EVENTS:
        return True
    return any(event_type.startswith(p) for p in ALLOWED_PATTERNS)
