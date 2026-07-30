"""端到端测试：旅游攻略 A2A 购买 → 交付。"""
import sys
import os
import json
import asyncio
import httpx

BASE = r"e:\SenAHo\书稿编写\智能体交易案例实践\act-autonomous-payment-demo"
sys.path.insert(0, BASE)

SELLER_URL = "http://127.0.0.1:8001"
DELEGATION_URL = "http://127.0.0.1:8000"
PSP_URL = "http://127.0.0.1:8002"

BUYER_AGENT_ID = "urn:demo:agent:buyer:001"
SELLER_AGENT_ID = "urn:demo:agent:seller:research-service-001"
SUB_ACCOUNT_ID = "subacct_buyer_001"
UAB_ID = "uab_demo_001"
PAYBIND_ID = "paybind_buyer_001"


async def setup_delegation():
    """初始化委托服务：复用已有身份或创建新的，然后创建意图和 IAC。"""
    print("[Setup] 初始化委托服务数据...")
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. 检查买方身份是否已存在 → 复用已注册的 credential_id
        resp = await client.get(f"{DELEGATION_URL}/v1/identities/{BUYER_AGENT_ID}")
        if resp.status_code == 200:
            buyer_identity = resp.json()
            credential_id = buyer_identity["credential_id"]
            print(f"  复用已有买方身份: credential_id={credential_id}")
        else:
            resp = await client.post(
                f"{DELEGATION_URL}/v1/identities",
                json={
                    "agent_id": BUYER_AGENT_ID,
                    "agent_id_scheme": "demo",
                    "service_endpoint": "http://127.0.0.1:58000",
                },
            )
            if resp.status_code != 200:
                print(f"  创建买方身份失败: {resp.status_code} {resp.text}")
                return None
            buyer_identity = resp.json()
            credential_id = buyer_identity["credential_id"]
            print(f"  新建买方身份: credential_id={credential_id}")

        # 2. 创建委托人-买方绑定（幂等：已存在则忽略）
        resp = await client.post(
            f"{DELEGATION_URL}/v1/user-agent-bindings",
            json={
                "user_agent_binding_id": UAB_ID,
                "delegator_id": "delegator_demo_001",
                "buyer_agent_id": BUYER_AGENT_ID,
            },
        )
        if resp.status_code == 200:
            print(f"  UAB: {UAB_ID}")
        else:
            # 可能已存在，忽略错误
            print(f"  UAB: {UAB_ID} (可能已存在, status={resp.status_code})")

        # 3. 创建支付绑定（幂等）
        resp = await client.post(
            f"{DELEGATION_URL}/v1/payment-bindings",
            json={
                "payment_binding_id": PAYBIND_ID,
                "user_agent_binding_id": UAB_ID,
                "buyer_agent_id": BUYER_AGENT_ID,
                "payment_method_id": "urn:demo:payment:local-balance:v1",
                "sub_account_id": SUB_ACCOUNT_ID,
            },
        )
        if resp.status_code == 200:
            print(f"  PaymentBinding: {PAYBIND_ID}")
        else:
            print(f"  PaymentBinding: {PAYBIND_ID} (可能已存在, status={resp.status_code})")

        # 4. 创建意图（ISR）
        resp = await client.post(
            f"{DELEGATION_URL}/v1/intents",
            json={
                "task_goal": "购买旅游攻略服务",
                "agent_id": BUYER_AGENT_ID,
                "agent_id_scheme": "demo",
                "user_agent_binding_id": UAB_ID,
                "max_total_amount": "5.00",
                "max_single_amount": "1.00",
                "currency": "CNY",
                "allowed_sellers": [SELLER_AGENT_ID],
                "allowed_categories": ["utility", "document.office", "lifestyle.travel"],
                "allowed_payment_methods": ["urn:demo:payment:local-balance:v1"],
                "validity_minutes": 30,
                "delegator_id": "delegator_demo_001",
            },
        )
        if resp.status_code != 200:
            print(f"  创建意图失败: {resp.status_code} {resp.text}")
            return None
        intent = resp.json()
        intent_id = intent["intent_id"]
        print(f"  Intent: {intent_id}")

        # 5. 签发 IAC（BOUNDED 模式）
        resp = await client.post(
            f"{DELEGATION_URL}/v1/delegations",
            json={"intent_id": intent_id},
        )
        if resp.status_code != 200:
            print(f"  签发 IAC 失败: {resp.status_code} {resp.text}")
            return None
        delegation = resp.json()
        delegation_id = delegation["delegation_id"]
        print(f"  Delegation: {delegation_id}")

        return {
            "credential_id": credential_id,
            "delegation_id": delegation_id,
            "session_id": "test_e2e_session_001",
        }


async def main():
    print("=" * 60)
    print("端到端测试：旅游攻略 A2A 购买交付流程")
    print("=" * 60)

    # ---- Setup: 初始化委托数据 ----
    setup = await setup_delegation()
    if not setup:
        print("委托初始化失败，退出")
        return
    credential_id = setup["credential_id"]
    delegation_id = setup["delegation_id"]
    session_id = setup["session_id"]

    # ---- Step 2: Create A2A Task ----
    print("\n[2] 创建 A2A Task...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks",
            json={
                "buyer_agent_id": BUYER_AGENT_ID,
                "goal": "购买服务: 旅游攻略生成",
                "delegation_id": delegation_id,
            },
        )
        assert resp.status_code == 200, f"创建 Task 失败: {resp.text}"
        task_data = resp.json()
        task_id = task_data["task_id"]
        print(f"   Task ID: {task_id}")
        print(f"   状态: {task_data['status']}")

    # ---- Step 3: Send Message to Seller ----
    print("\n[3] 发送购买消息给卖家...")
    destination = "杭州"
    departure = "北京"
    days = 3

    message_content = (
        f"你好，我需要一份旅游攻略。\n"
        f"目的地: {destination}\n"
        f"出发地: {departure}\n"
        f"游玩天数: {days} 天\n"
        f"委托ID: {delegation_id}"
    )
    print(f"   消息: {message_content[:100]}...")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks/{task_id}/messages",
            json={
                "content": message_content,
                "sender_role": "buyer_agent",
                "delegation_id": delegation_id,
                "credential_id": credential_id,
                "session_id": session_id,
            },
        )
        assert resp.status_code == 200, f"发送消息失败: {resp.text}"
        msg_result = resp.json()

        seller_response = msg_result.get("response_text", "")
        task_result = msg_result.get("result", {})

        print(f"   卖家回复: {seller_response}")
        print(f"   任务状态: {task_result.get('status', '?')}")

    # ---- Step 4: Handle Payment ----
    skill_id = msg_result.get("skill_id", "")

    if task_result.get("status") == "PAYMENT_REQUIRED":
        payment_needed_raw = task_result.get("payment_needed", {})
        payment_needed = payment_needed_raw.get("payment_needed", payment_needed_raw)
        amount = payment_needed.get("amount", "?")
        print(f"\n[4] 卖家要求支付: {amount} CNY")

        service_id = task_result.get("service_id", "")
        print(f"   Service ID: {service_id}, Skill ID: {skill_id}")

    else:
        print(f"\n[4] 异常: 期望 PAYMENT_REQUIRED，实际: {task_result.get('status')}")
        print(f"   Full: {json.dumps(msg_result, ensure_ascii=False, indent=2)[:500]}")
        return

    # ---- Step 5: Execute Payment (PSP on port 8002) ----
    print(f"\n[5] 执行 PSP 支付 ({PSP_URL})...")
    async with httpx.AsyncClient(timeout=30) as client:
        psp_resp = await client.post(
            f"{PSP_URL}/v1/payments",
            json={
                "request_id": f"req_{delegation_id}",
                "delegation_id": delegation_id,
                "user_agent_binding_id": UAB_ID,
                "payment_binding_id": PAYBIND_ID,
                "agent_credential_ref": credential_id,
                "sub_account_id": SUB_ACCOUNT_ID,
                "out_trade_no": payment_needed.get("out_trade_no", ""),
                "resource_id": payment_needed.get("resource_id", ""),
                "resource_digest": payment_needed.get("resource_digest", ""),
                "service_id": service_id,
                "service_category": payment_needed.get("service_category", ""),
                "seller_id": payment_needed.get("seller_unique_id", SELLER_AGENT_ID),
                "buyer_agent_id": BUYER_AGENT_ID,
                "amount": amount,
                "currency": payment_needed.get("currency", "CNY"),
                "method_id": payment_needed.get("method_id", "urn:demo:payment:local-balance:v1"),
                "session_id": session_id,
                "task_id": task_id,
                "signature": "placeholder",
            },
        )
        print(f"   支付响应: {psp_resp.status_code}")
        if psp_resp.status_code != 200:
            print(f"   支付失败: {psp_resp.text[:500]}")
            return
        pay_data = psp_resp.json()
        trade_no = pay_data.get("trade_no")
        print(f"   PSP 支付成功! trade_no={trade_no}")
        print(f"   新余额: {pay_data.get('new_balance')} CNY")

    # ---- Step 6: Pay A2A Task (触发履约) ----
    print(f"\n[6] 支付 A2A Task (trade_no: {trade_no})...")
    input_data = {
        "destination_city": destination,
        "departure_city": departure,
        "days": days,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{SELLER_URL}/v1/a2a/tasks/{task_id}/pay",
            json={
                "service_id": service_id,
                "skill_id": skill_id,
                "input_data": input_data,
                "payment_proof": {"trade_no": trade_no},
                "trade_no": trade_no,
            },
        )
        print(f"   支付端点响应: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   错误: {resp.text}")
            return
        fulfill = resp.json()
        print(f"   履约状态: {fulfill.get('status')}")

        if fulfill.get("status") != "FULFILLED":
            print(f"   失败: {fulfill.get('error', '')}")
            return

        artifact = fulfill.get("artifact", {})
        print(f"   Artifact ID: {artifact.get('artifact_id', '?')}")
        payload = artifact.get("payload", {})
        print(f"   输出文件: {payload.get('output_filename', '?')}")
        print(f"   方法: {payload.get('method', '?')}")

    # ---- Step 7: Get Artifacts ----
    print("\n[7] 获取 Artifacts...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{SELLER_URL}/v1/a2a/tasks/{task_id}/artifacts")
        print(f"   响应: {resp.status_code}")
        if resp.status_code == 200:
            artifacts = resp.json()
            print(f"   Artifacts 数量: {len(artifacts)}")
            for a in artifacts:
                print(f"   - {a.get('artifact_id')}: {a.get('artifact_type')}")

    # ---- Step 8: Download File ----
    print("\n[8] 下载交付文件...")
    output_file_id = payload.get("output_file_id", "")
    if output_file_id:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"http://127.0.0.1:8080/api/files/{output_file_id}/download"
            )
            print(f"   下载响应: {resp.status_code}")
            if resp.status_code == 200:
                test_out = os.path.join(BASE, "data", "test_output.docx")
                with open(test_out, "wb") as f:
                    f.write(resp.content)
                file_size = os.path.getsize(test_out)
                print(f"   保存到: {test_out}")
                print(f"   文件大小: {file_size} bytes")
                # 读取 .md 文件内容
                with open(test_out, "r", encoding="utf-8") as f:
                    md_content = f.read()
                lines = md_content.split("\n")
                print(f"   行数: {len(lines)}")
                print(f"   前5行:")
                for line in lines[:5]:
                    print(f"     -> {line[:100]}")
            else:
                print(f"   下载失败: {resp.text[:200]}")
    else:
        print("   没有 output_file_id！")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


asyncio.run(main())
