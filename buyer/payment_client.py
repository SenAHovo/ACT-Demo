"""支付客户端 — 解析 HTTP 402 Payment-Needed 并调用 PSP。"""
import os, uuid, httpx
from decimal import Decimal

PSP_URL = os.getenv("DEMO_PSP_URL", "http://127.0.0.1:8002")
BUYER_ID = "urn:demo:agent:buyer:001"

def parse_payment_needed(resp_json: dict, headers: dict) -> dict:
    pn = resp_json.get("payment_needed", resp_json)
    return {
        "method_id": pn.get("method_id", ""),
        "psp_id": pn.get("psp_id", ""),
        "endpoint": pn.get("endpoint", ""),
        "out_trade_no": pn.get("out_trade_no", ""),
        "amount": pn.get("amount", "0"),
        "currency": pn.get("currency", "CNY"),
        "resource_id": pn.get("resource_id", ""),
        "resource_digest": pn.get("resource_digest", ""),
        "service_id": pn.get("service_id", ""),
        "service_category": pn.get("service_category", ""),
        "session_id": pn.get("session_id", ""),
        "task_id": pn.get("task_id", ""),
        "seller_unique_id": pn.get("seller_unique_id", ""),
    }

async def execute_payment(
    pn: dict, delegation: dict, session_id: str, task_id: str,
    credential_id: str,
) -> dict | None:
    """构造支付请求 → 调 PSP → 返回完整结果（含 trade_no、proof、new_balance）。

    返回完整 PSP 响应是 ACT 支付凭证链的要求：买方智能体必须将 PSP
    签发的支付凭证（proof）完整传递给卖方，卖方才能独立验证金额、
    卖方 ID、买方 ID 是否匹配，实现不可抵赖的支付证明。
    """
    req = {
        "request_id": f"req_{uuid.uuid4().hex[:16]}",
        "delegation_id": delegation["delegation_id"],
        "user_agent_binding_id": delegation.get("user_agent_binding_id", "uab_demo_001"),
        "payment_binding_id": "paybind_buyer_001",
        "agent_credential_ref": credential_id,
        "sub_account_id": "subacct_buyer_001",
        "out_trade_no": pn["out_trade_no"],
        "resource_id": pn["resource_id"],
        "resource_digest": pn["resource_digest"],
        "service_id": pn["service_id"],
        "service_category": pn["service_category"],
        "seller_id": pn.get("seller_unique_id", "urn:demo:agent:seller:research-service-001"),
        "buyer_agent_id": BUYER_ID,
        "amount": pn["amount"],
        "currency": pn["currency"],
        "method_id": pn["method_id"],
        "session_id": session_id,
        "task_id": task_id,
        "signature": "placeholder",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{PSP_URL}/v1/payments", json=req)
        if resp.status_code == 200:
            data = resp.json()
            trade_no = data.get("trade_no", "")
            print(f"[Payment] 支付成功: {pn['amount']} CNY, trade_no={trade_no}")
            return data  # 返回完整结果：trade_no, proof, new_balance
        else:
            print(f"[Payment] 支付失败: {resp.status_code} {resp.text}")
            return None
