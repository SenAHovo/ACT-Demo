"""
身份工具模块

智能体身份标识的生成、校验和方案管理。
所有 urn:demo:agent:* 标识必须声明 agent_id_scheme="demo"。
"""

import uuid
import re

AGENT_ID_SCHEME = "demo"
URN_PREFIX = "urn:demo:agent:"

# urn:demo:agent:{role}:{id} 格式
AGENT_ID_PATTERN = re.compile(r"^urn:demo:agent:[a-z_]+:[a-zA-Z0-9_-]+$")


def generate_agent_id(role: str) -> str:
    """生成 demo 方案下的智能体标识。"""
    return f"{URN_PREFIX}{role}:{uuid.uuid4().hex[:8]}"


def validate_agent_id(agent_id: str) -> None:
    """校验 agent_id 格式，不符合则抛出 ValueError。"""
    if not AGENT_ID_PATTERN.match(agent_id):
        raise ValueError(
            f"无效的 agent_id: {agent_id}，"
            f"必须匹配格式 urn:demo:agent:{{role}}:{{id}}"
        )


def validate_agent_id_scheme(scheme: str) -> None:
    """校验 agent_id_scheme 必须为 'demo'。"""
    if scheme != AGENT_ID_SCHEME:
        raise ValueError(
            f"agent_id_scheme 必须为 '{AGENT_ID_SCHEME}'，实际为: {scheme}"
        )


def generate_credential_id() -> str:
    """生成本地凭证标识。"""
    return f"cred_demo_{uuid.uuid4().hex[:12]}"


def generate_binding_id(prefix: str) -> str:
    """生成绑定标识，如 uab_xxx / paybind_xxx。"""
    return f"{prefix}_demo_{uuid.uuid4().hex[:8]}"
