"""Phase 1 验证脚本 — shared/ 模块功能测试"""

from shared.money import parse_amount, validate_currency, assert_amount_not_exceed
from shared.time_utils import utc_now, to_iso, minutes_from_now
from shared.encoding import b64url_encode, b64url_decode
from shared.canonicalization import jcs_canonicalize
from shared.signatures import generate_keypair, sign_json, verify_json, compute_sha256_digest
from shared.errors import ErrorCode, AppError
from shared.identity import validate_agent_id, validate_agent_id_scheme, generate_agent_id
from shared.schemas import IAC, PaymentProof, ServiceArtifact, TaskBill, ISR

from datetime import datetime, timezone
from decimal import Decimal

def test_money():
    assert parse_amount("0.50") == parse_amount("0.5")
    assert validate_currency("cny") == "CNY"
    assert_amount_not_exceed(Decimal("0.30"), Decimal("0.50"), "test")
    try:
        assert_amount_not_exceed(Decimal("1.00"), Decimal("0.50"))
        assert False, "should raise"
    except ValueError:
        pass
    print("[OK] money")

def test_time():
    now = utc_now()
    iso = to_iso(now)
    future = minutes_from_now(30)
    assert future > now
    print("[OK] time_utils")

def test_encoding():
    encoded = b64url_encode(b"hello")
    assert b64url_decode(encoded) == b"hello"
    print("[OK] encoding")

def test_canonicalization():
    canon = jcs_canonicalize({"b": 2, "a": 1})
    assert canon.index(b'"a"') < canon.index(b'"b"')  # sorted keys
    print("[OK] canonicalization")

def test_signatures():
    priv, pub = generate_keypair()
    obj = {"test": "data", "value": 123}
    sig = sign_json(priv, obj)
    assert verify_json(pub, obj, sig)
    assert not verify_json(pub, {"test": "modified"}, sig)
    digest = compute_sha256_digest(obj)
    assert len(digest) == 64
    print("[OK] signatures")

def test_identity():
    validate_agent_id("urn:demo:agent:buyer:001")
    validate_agent_id_scheme("demo")
    uid = generate_agent_id("buyer")
    assert uid.startswith("urn:demo:agent:buyer:")
    try:
        validate_agent_id("invalid-id")
        assert False
    except ValueError:
        pass
    print("[OK] identity")

def test_schemas():
    now = utc_now()
    future = minutes_from_now(30)
    iac = IAC(
        delegation_id="del_001", intent_id="int_001", delegator_id="user_001",
        agent_id="urn:demo:agent:buyer:001", user_agent_binding_id="uab_001",
        validity_start_time=now, validity_end_time=future,
        max_total_amount=Decimal("1.00"), max_single_amount=Decimal("0.50"),
        allowed_sellers=["urn:demo:agent:seller:research-service-001"],
        allowed_categories=["data.industry", "analysis.industry", "report.industry"],
        allowed_payment_methods=["urn:demo:payment:local-balance:v1"],
        source_isr_digest="sha256:abc",
        status_reference="http://127.0.0.1:8000/v1/delegations/del_001",
        proof="sig_base64url",
    )
    data = iac.model_dump()
    assert data["delegation_id"] == "del_001"
    assert float(data["max_total_amount"]) == 1.0
    print("[OK] schemas")

def test_errors():
    err = AppError(ErrorCode.INSUFFICIENT_BALANCE, "余额不足")
    assert err.code == ErrorCode.INSUFFICIENT_BALANCE
    print("[OK] errors")

if __name__ == "__main__":
    test_money()
    test_time()
    test_encoding()
    test_canonicalization()
    test_signatures()
    test_identity()
    test_schemas()
    test_errors()
    print("\n=== ALL shared/ module tests PASSED ===")
