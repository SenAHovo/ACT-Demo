"""
签名工具模块

基于 Ed25519 的签名生成和验证。
使用 cryptography 库实现。
"""

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .encoding import b64url_encode, b64url_decode
from .canonicalization import jcs_canonicalize


def generate_keypair() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """生成 Ed25519 密钥对。"""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def private_key_to_pem(private_key: ed25519.Ed25519PrivateKey) -> str:
    """将私钥序列化为 PEM 字符串。"""
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


def public_key_to_pem(public_key: ed25519.Ed25519PublicKey) -> str:
    """将公钥序列化为 PEM 字符串。"""
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("ascii")


def load_private_key(pem_str: str) -> ed25519.Ed25519PrivateKey:
    """从 PEM 字符串加载私钥。"""
    return serialization.load_pem_private_key(pem_str.encode("ascii"), password=None)


def load_public_key(pem_str: str) -> ed25519.Ed25519PublicKey:
    """从 PEM 字符串加载公钥。"""
    return serialization.load_pem_public_key(pem_str.encode("ascii"))


def public_key_to_b64(public_key: ed25519.Ed25519PublicKey) -> str:
    """将公钥导出为 Base64URL 字符串（原始 32 字节）。"""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return b64url_encode(raw)


def sign_json(private_key: ed25519.Ed25519PrivateKey, obj: object) -> str:
    """
    对对象进行 JCS 规范化后签名，返回 Base64URL 签名字符串。
    """
    canonical = jcs_canonicalize(obj)
    signature = private_key.sign(canonical)
    return b64url_encode(signature)


def verify_json(
    public_key: ed25519.Ed25519PublicKey, obj: object, signature_b64: str
) -> bool:
    """
    验证对象（JCS 规范化后）的 Ed25519 签名。
    """
    canonical = jcs_canonicalize(obj)
    signature = b64url_decode(signature_b64)
    try:
        public_key.verify(signature, canonical)
        return True
    except InvalidSignature:
        return False


def compute_sha256_digest(obj: object) -> str:
    """
    计算对象的 SHA-256 摘要（JCS 规范化 + SHA-256），返回 hex 字符串。
    """
    canonical = jcs_canonicalize(obj)
    return hashlib.sha256(canonical).hexdigest()
