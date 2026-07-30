"""
shared/ — 共享数据结构与工具模块

为所有服务模块提供统一的数据模型定义、加解密工具、编码工具和通用错误码。
"""

from .money import parse_amount, validate_currency, assert_amount_not_exceed
from .time_utils import utc_now, to_iso, from_iso, is_expired, minutes_from_now
from .encoding import b64url_encode, b64url_decode
from .canonicalization import jcs_canonicalize
from .signatures import (
    generate_keypair,
    private_key_to_pem,
    public_key_to_pem,
    load_private_key,
    load_public_key,
    public_key_to_b64,
    sign_json,
    verify_json,
    compute_sha256_digest,
)
from .errors import ErrorCode, AppError
from .identity import (
    AGENT_ID_SCHEME,
    generate_agent_id,
    validate_agent_id,
    validate_agent_id_scheme,
    generate_credential_id,
    generate_binding_id,
)
from .bindings import UserAgentBinding, PaymentBinding
from .interaction import (
    DataItem,
    ArtifactRef,
    InteractionEnvelope,
    generate_interaction_id,
)
from .schemas import (
    AgentIdentityRecord,
    AuthenticationAssertion,
    ISR,
    IAC,
    ServiceOffer,
    ServiceInvocation,
    PaymentNeeded,
    PaymentRequest,
    PaymentProof,
    ServiceArtifact,
    AttestationRecord,
    TaskBill,
    TaskBillPayment,
)

__all__ = [
    # money
    "parse_amount",
    "validate_currency",
    "assert_amount_not_exceed",
    # time
    "utc_now",
    "to_iso",
    "from_iso",
    "is_expired",
    "minutes_from_now",
    # encoding
    "b64url_encode",
    "b64url_decode",
    # canonicalization
    "jcs_canonicalize",
    # signatures
    "generate_keypair",
    "private_key_to_pem",
    "public_key_to_pem",
    "load_private_key",
    "load_public_key",
    "public_key_to_b64",
    "sign_json",
    "verify_json",
    "compute_sha256_digest",
    # errors
    "ErrorCode",
    "AppError",
    # identity
    "AGENT_ID_SCHEME",
    "generate_agent_id",
    "validate_agent_id",
    "validate_agent_id_scheme",
    "generate_credential_id",
    "generate_binding_id",
    # bindings
    "UserAgentBinding",
    "PaymentBinding",
    # interaction
    "DataItem",
    "ArtifactRef",
    "InteractionEnvelope",
    "generate_interaction_id",
    # schemas
    "AgentIdentityRecord",
    "AuthenticationAssertion",
    "ISR",
    "IAC",
    "ServiceOffer",
    "ServiceInvocation",
    "PaymentNeeded",
    "PaymentRequest",
    "PaymentProof",
    "ServiceArtifact",
    "AttestationRecord",
    "TaskBill",
    "TaskBillPayment",
]
