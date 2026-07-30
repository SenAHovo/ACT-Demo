"""
JSON 规范化模块

实现 RFC 8785 JSON Canonicalization Scheme (JCS)。
用于签名和摘要前的 JSON 规范化。
"""

import json


def jcs_canonicalize(obj: object) -> bytes:
    """
    按 RFC 8785 JCS 规范将对象规范化为 bytes。

    规则:
    - 对象键按字典序排序
    - 字符串使用 Unicode 转义最小化
    - 数字保留必要精度
    - 无缩进，无尾随换行（除 LF）
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
