"""
编码工具模块

Base64URL 编解码（无填充，URL 安全）。
"""

import base64


def b64url_encode(data: bytes) -> str:
    """将 bytes 编码为 Base64URL 字符串（无填充）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    """从 Base64URL 字符串解码为 bytes（自动补全填充）。"""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)
