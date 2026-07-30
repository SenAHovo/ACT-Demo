"""
JSON 规范化模块

提供教学性确定性 JSON 序列化：对象键排序 + 紧凑无缩进 JSON。
用于签名和摘要前的 JSON 规范化。

注意：本实现采用简化确定性序列化策略（键排序 + 紧凑 JSON），
未完整实现 RFC 8785 JCS（如浮点数指数表达、完整 Unicode 转义规则等）。
"""

import json


def jcs_canonicalize(obj: object) -> bytes:
    """
    将对象按教学性确定性序列化规则规范化为 bytes。

    规则:
    - 对象键按字典序排序
    - 紧凑无缩进 JSON（无尾随换行）
    - 禁止 NaN/Infinity

    注意：使用标准 json.dumps 实现确定性序列化，未完整实现 RFC 8785。
    """
    serialized = json.dumps(
        obj,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
        sort_keys=True,
    )
    return serialized.encode("utf-8")
