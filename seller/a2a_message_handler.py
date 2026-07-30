"""
A2A Message Handler — 卖家智能体接收买家消息后的处理逻辑（案例内部协议）

卖家 LLM 解析买家消息意图 → 调度 Skill 执行 → 生成 Artifact → 处理支付
"""
from __future__ import annotations

import asyncio
import json
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.time_utils import utc_now, to_iso
from shared.errors import ErrorCode, AppError
from shared.signatures import compute_sha256_digest
from shared.console_colors import cprint, DIM
from .database import get_db
from .catalog import get_service
from .skill_registry import execute_skill
from .a2a_task_manager import update_task_status, get_task

# PSP 支付服务地址
PSP_URL = os.getenv("PSP_URL", "http://127.0.0.1:8002")

# 卖家 LLM 配置（复用 DeepSeek 适配器）
SELLER_SYSTEM_PROMPT = """你是 ACT 协议中的「文档与生活服务智能体」（卖方）。

你的职责是接收买方智能体的 A2A 任务消息，理解其意图后调度相应技能完成服务交付。

## 可用技能
- weekly-report-generation: 周报生成
  * 需要 template_file_id（用户上传的 DOCX 模板）、work_items（工作内容列表 [{"date":"...","content":"..."}]）
  * 可选 author、department、week_range、language_style
- travel-guide-generation: 旅游攻略生成
  * 需要 destination_city（目的地）、departure_city（出发地）、days（天数）
  * 可选 preferences（偏好）、budget（预算级别）
- translation: 多语言翻译
  * 文件模式: 需要 file_id
  * 文本模式: 需要 text
  * 支持 zh↔en, zh↔ja, zh↔ko

## 意图识别规则（重要！）
你必须根据买家消息中的关键词精确判断 skill_id：
1. **旅游攻略** (travel-guide-generation): 消息中出现"旅游"、"攻略"、"目的地"、"出发地"、"游玩"、"几天"、"景点"等词 → 选 travel-guide-generation
2. **周报生成** (weekly-report-generation): 消息中出现"周报"、"工作内容"、"本周工作"、"下周计划"、"模板"等词 → 选 weekly-report-generation
3. **翻译** (translation): 消息中出现"翻译"、"translate"、"译"等词，或包含待翻译的文本/文件 → 选 translation

注意：如果消息中同时出现旅游关键词（如"杭州"、"北京"、"3天"）和工作关键词，优先根据是否有"攻略/旅游"等词判断。明确包含"旅游攻略"/"攻略"的消息应该选 travel-guide-generation。

## 规则
1. 从买方消息中仔细提取服务意图和所有参数
2. 周报生成：必须有模板文件 ID 和工作内容才能执行，否则在 response_text 中告知缺少
3. 旅游攻略：必须有目的地、出发地和天数
4. 翻译：必须有文件 ID 或文本内容
5. response_text 必须详细说明理解的买方需求、具体参数、费用
6. 严格以 JSON 格式输出: {"skill_id": "...", "params": {...}, "response_text": "给买方的回复"}

## 语言
始终使用中文回复。"""


async def handle_task_message(
    task_id: str,
    sender_role: str,
    content: str,
    delegation_id: str = "",
) -> dict:
    """
    处理发往 Task 的消息。

    流程:
    1. 存储消息
    2. 更新 Task 状态 → PROCESSING
    3. LLM 解析消息意图
    4. 调度 Skill 执行
    5. 生成 Artifact
    6. 返回结果（含支付信息或交付结果）
    """
    now_iso = to_iso(utc_now())
    message_id = f"a2a_msg_{uuid.uuid4().hex[:16]}"

    # ---- 1. 存储消息 ----
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO a2a_messages (message_id, task_id, sender_role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, task_id, sender_role, content, now_iso),
        )
        await db.commit()
    finally:
        await db.close()

    # ---- 2. 更新任务状态 ----
    task = await get_task(task_id)
    if task["status"] == "CREATED":
        await update_task_status(task_id, "PROCESSING")

    # ---- 3. LLM 解析意图 ----
    skill_id, params, buyer_response = await _parse_message_intent(content)

    # ---- 4. 执行 Skill ----
    skill_result = await _execute_skill_with_payment(
        task_id, skill_id, params, delegation_id
    )

    # ---- 5. 返回结果 ----
    return {
        "message_id": message_id,
        "task_id": task_id,
        "skill_id": skill_id,
        "response_text": buyer_response,
        "result": skill_result,
    }


async def _parse_message_intent(content: str) -> tuple[str, dict, str]:
    """使用 LLM 解析买家消息意图，返回 (skill_id, params, response_text)。"""
    content_lower = content.lower()

    # ---- 关键词预路由（比 LLM 更可靠） ----
    # 旅游攻略关键词
    travel_keywords = ["旅游", "攻略", "目的地", "出发地", "游玩", "景点", "旅行", "出游", "行程"]
    # 周报关键词
    report_keywords = ["周报", "工作内容", "本周工作", "下周计划", "工作总结", "汇报"]
    # 翻译关键词
    translation_keywords = ["翻译", "translate", "译", "中译英", "英译中"]

    has_travel = any(kw in content for kw in travel_keywords)
    has_report = any(kw in content for kw in report_keywords)
    has_translation = any(kw in content for kw in translation_keywords)

    # 如果明确命中旅游关键词，直接路由
    if has_travel and not has_report and not has_translation:
        return _parse_travel_params(content)

    # 如果明确命中周报关键词
    if has_report and not has_travel and not has_translation:
        return _parse_report_params(content)

    # 如果明确命中翻译关键词
    if has_translation and not has_travel and not has_report:
        return _parse_translation_params(content)

    # 关键词冲突或无法判断 → 回退到 LLM
    from llm.config import get_llm_config
    from llm.deepseek_adapter import DeepSeekAdapter

    config = get_llm_config("buyer")
    llm = DeepSeekAdapter(config)

    messages = [
        {"role": "system", "content": SELLER_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    try:
        raw = llm.chat_json(messages, temperature=0.1, max_tokens=1024)
        skill_id = raw.get("skill_id", "translation")
        params = raw.get("params", {})
        response_text = raw.get("response_text", "收到，正在为您处理。")
        return skill_id, params, response_text
    except Exception:
        return "translation", {"text": content, "source_lang": "zh", "target_lang": "en"}, "已收到您的请求，正在处理。"


def _parse_travel_params(content: str) -> tuple[str, dict, str]:
    """从消息中提取旅游攻略参数。"""
    import re
    params = {}

    # 提取目的地
    dest_match = re.search(r'目的地[：:\s]*(\S+)', content)
    if dest_match:
        params["destination_city"] = dest_match.group(1).strip("，,。.")

    # 提取出发地
    dep_match = re.search(r'出发地[：:\s]*(\S+)', content)
    if dep_match:
        params["departure_city"] = dep_match.group(1).strip("，,。.")

    # 提取天数
    days_match = re.search(r'(\d+)\s*天', content)
    if days_match:
        params["days"] = int(days_match.group(1))

    # 提取偏好
    pref_match = re.search(r'偏好[：:\s]*(\S+)', content)
    if pref_match:
        params["preferences"] = pref_match.group(1).strip("，,。.")

    missing = []
    if "destination_city" not in params:
        missing.append("目的地")
    if "departure_city" not in params:
        missing.append("出发地")
    if "days" not in params:
        missing.append("游玩天数")

    if missing:
        response = f"收到您的旅游攻略需求。但缺少以下信息: {', '.join(missing)}，请补充后重新发送。"
    else:
        response = (
            f"您好！已收到您的旅游攻略需求。"
            f"您计划从{params['departure_city']}出发，前往{params['destination_city']}游玩{params['days']}天。"
            f"费用为 0.35 CNY，请完成支付后我将为您生成详细的旅游攻略。"
        )

    return "travel-guide-generation", params, response


def _parse_report_params(content: str) -> tuple[str, dict, str]:
    """从消息中提取周报参数。"""
    import re
    params = {}

    # 提取模板文件ID
    tmpl_match = re.search(r'(?:模板文件|模板)[IDid：:\s]*[（(]?(\S+?)[）)]?(?:\s|$|，|,|。)', content)
    if tmpl_match:
        params["template_file_id"] = tmpl_match.group(1).strip()

    # 提取报告人
    author_match = re.search(r'报告人[：:\s]*(\S+)', content)
    if author_match:
        params["author"] = author_match.group(1).strip("，,。.")

    # 提取部门
    dept_match = re.search(r'部门[：:\s]*(\S+)', content)
    if dept_match:
        params["department"] = dept_match.group(1).strip("，,。.")

    # 提取周范围
    week_match = re.search(r'周范围[：:\s]*(\S+)', content)
    if week_match:
        params["week_range"] = week_match.group(1).strip("，,。.")

    # 提取语言风格
    style_match = re.search(r'(?:语言|风格)[：:\s]*(\S+)', content)
    if style_match:
        params["language_style"] = style_match.group(1).strip("，,。.")

    missing = []
    if "template_file_id" not in params:
        missing.append("模板文件ID（请先上传DOCX模板）")

    if missing:
        response = f"收到您的周报生成需求。但缺少以下信息: {', '.join(missing)}，请补充后重新发送。"
    else:
        response = (
            f"您好！已收到您的周报生成需求。"
            f"将使用指定的模板生成周报，费用为 0.30 CNY，请完成支付后我将为您生成周报。"
        )

    return "weekly-report-generation", params, response


def _parse_translation_params(content: str) -> tuple[str, dict, str]:
    """从消息中提取翻译参数。"""
    import re
    lang_map = {"中文": "zh", "english": "en", "英文": "en", "日文": "ja", "日语": "ja", "韩文": "ko", "韩语": "ko"}
    params = {"source_lang": "zh", "target_lang": "en"}

    # 提取文件ID
    file_match = re.search(r'(?:文件|file)[IDid：:\s]*[（(]?(\S+?)[）)]?(?:\s|$|，|,|。)', content)
    if file_match:
        params["file_id"] = file_match.group(1).strip()

    # ---- 判断语言方向 ----
    # 尝试从 "从{lang}翻译到{lang}" 或 "{lang}→{lang}" 模式中提取
    lang_pattern = r'(?:从|将)?\s*(中文|英文|english|日文|日语|韩文|韩语)\s*(?:翻译(?:到|成|为)|译为|→|->)\s*(中文|英文|english|日文|日语|韩文|韩语)'
    lang_match = re.search(lang_pattern, content, re.IGNORECASE)
    if lang_match:
        src = lang_map.get(lang_match.group(1), "")
        tgt = lang_map.get(lang_match.group(2), "")
        if src and tgt:
            params["source_lang"] = src
            params["target_lang"] = tgt

    # 回退：检测特定缩写/关键词
    if params["source_lang"] == "zh" and params["target_lang"] == "en":
        if "英译中" in content or "en→zh" in content.lower() or "en2zh" in content.lower():
            params["source_lang"] = "en"
            params["target_lang"] = "zh"
        elif "中译日" in content or "zh→ja" in content.lower():
            params["source_lang"] = "zh"
            params["target_lang"] = "ja"
        elif "中译韩" in content or "zh→ko" in content.lower():
            params["source_lang"] = "zh"
            params["target_lang"] = "ko"
        elif "日译中" in content or "ja→zh" in content.lower():
            params["source_lang"] = "ja"
            params["target_lang"] = "zh"
        elif "韩译中" in content or "ko→zh" in content.lower():
            params["source_lang"] = "ko"
            params["target_lang"] = "zh"

    # 提取文本内容
    text_match = re.search(r'(?:原文|文本|内容)[：:\s]*"?(.+?)"?$', content, re.DOTALL)
    if text_match and not params.get("file_id"):
        params["text"] = text_match.group(1).strip()

    if "file_id" not in params and "text" not in params:
        response = "收到您的翻译需求。请提供要翻译的文件ID或文本内容。"
    else:
        response = (
            f"您好！已收到您的翻译需求。"
            f"将从{params['source_lang']}翻译到{params['target_lang']}，费用为 0.15 CNY，请完成支付后我将为您翻译。"
        )

    return "translation", params, response


async def _execute_skill_with_payment(
    task_id: str,
    skill_id: str,
    params: dict,
    delegation_id: str,
) -> dict:
    """
    执行 Skill 并处理支付流程。

    返回:
        - 如果需支付: {"status": "PAYMENT_REQUIRED", "payment_needed": {...}}
        - 如果直接完成: {"status": "FULFILLED", "artifact": {...}}
    """
    # 映射 skill_id → service_id
    SKILL_TO_SERVICE = {
        "weekly-report-generation": "doc.weekly.report",
        "travel-guide-generation": "lifestyle.travel.guide",
        "translation": "utility.translation",
    }
    service_id = SKILL_TO_SERVICE.get(skill_id, skill_id)

    # 对于需要支付的服务，先检查是否有 delegation
    if delegation_id and service_id in SKILL_TO_SERVICE.values():
        return await _handle_paid_service_execution(
            task_id, skill_id, service_id, params, delegation_id
        )
    else:
        # 无委托 → 直接执行（仅用于不需要支付的服务或测试）
        return await _execute_service_directly(task_id, skill_id, service_id, params)


async def _handle_paid_service_execution(
    task_id: str,
    skill_id: str,
    service_id: str,
    params: dict,
    delegation_id: str,
) -> dict:
    """执行需支付的服务：先生成订单 → 返回 PAYMENT_REQUIRED → 买方支付后再执行。"""
    from .commerce_controller import _create_payment_needed, _execute_service, _extract_payment_proof_header
    from .catalog import get_service as get_svc

    svc = await get_svc(service_id)

    # 生成订单并返回付款要求
    invoke_id = f"invoke_{uuid.uuid4().hex[:16]}"
    session_id = f"a2a_session_{task_id}"

    payment_needed = await _create_payment_needed(invoke_id, svc, session_id, task_id)

    await update_task_status(task_id, "PAYMENT_REQUIRED")

    return {
        "status": "PAYMENT_REQUIRED",
        "service_id": service_id,
        "skill_id": skill_id,
        "payment_needed": payment_needed.get("payment_needed", {}),
        "message": f"请支付 {svc['price']} {svc['currency']} 以继续执行 {svc['name']}",
    }


async def execute_service_after_payment(
    task_id: str,
    service_id: str,
    skill_id: str,
    input_data: dict,
    payment_proof: dict,
    trade_no: str,
) -> dict:
    """支付完成后执行服务交付。

    ACT 规范流程:
    1. 查服务目录获取标价
    2. 验证支付凭证（含 seller_id 和 amount 独立校验）
    3. 防重放检查（proof_usage 表）
    4. 执行 Skill 生成成果
    5. 记录凭证使用
    6. 通知 PSP 交付完成
    7. 返回 Artifact
    """
    import httpx
    from .catalog import get_service as get_svc
    from .payment_adapter import verify_payment_proof as _seller_verify_proof

    svc = await get_svc(service_id)

    # ---- Step 1-2: 验证支付凭证（含 seller_id 和 amount 独立校验） ----
    if payment_proof:
        try:
            await _seller_verify_proof(payment_proof, expected_amount=svc["price"])
        except AppError as e:
            return {"status": "ERROR", "error": "PAYMENT_PROOF_INVALID", "message": str(e)}
        except Exception as e:
            return {"status": "ERROR", "error": "PSP_UNAVAILABLE", "message": f"无法连接 PSP: {e}"}

    # ---- Step 3: 防重放检查 ----
    db = await get_db()
    try:
        if trade_no:
            cursor = await db.execute(
                "SELECT usage_count FROM proof_usage WHERE trade_no = ?", (trade_no,)
            )
            row = await cursor.fetchone()
            if row and row["usage_count"] > 0:
                return {
                    "status": "ERROR",
                    "error": "PROOF_ALREADY_USED",
                    "message": f"支付凭证 {trade_no} 已被使用 {row['usage_count']} 次，禁止重复消费",
                }
    finally:
        await db.close()

    # ---- Step 4: 执行 Skill 生成成果 ----
    skill_result = await execute_skill(skill_id, input_data)

    # 生成 Artifact
    artifact_id = f"artifact_{uuid.uuid4().hex[:16]}"
    payload = skill_result.get("payload", {})
    content_digest = compute_sha256_digest(payload)

    now_iso = to_iso(utc_now())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO artifacts
               (artifact_id, artifact_type, session_id, task_id,
                service_id, trade_no, content_digest, payload, source_artifact_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                skill_result.get("artifact_type", "unknown"),
                f"a2a_session_{task_id}",
                task_id,
                service_id,
                trade_no or "",
                content_digest,
                json.dumps(payload),
                json.dumps(skill_result.get("source_artifact_ids", [])),
                now_iso,
            ),
        )

        # ---- Step 5: 记录支付凭证使用（防重放） ----
        if trade_no:
            await db.execute(
                """INSERT INTO proof_usage (trade_no, usage_count, first_used_at)
                   VALUES (?, 1, ?)
                   ON CONFLICT(trade_no) DO UPDATE SET
                   usage_count = usage_count + 1""",
                (trade_no, now_iso),
            )

        await db.commit()
    finally:
        await db.close()

    await update_task_status(task_id, "PAID")
    await update_task_status(task_id, "FULFILLED")

    # ---- Step 6: 通知 PSP 交付完成（ACT 规范要求卖家通知） ----
    if trade_no:
        asyncio.create_task(_notify_psp_fulfillment(trade_no))

    return {
        "status": "FULFILLED",
        "artifact": {
            "artifact_id": artifact_id,
            "artifact_type": skill_result.get("artifact_type"),
            "payload": payload,
            "service_id": service_id,
            "created_at": now_iso,
        },
    }


async def _notify_psp_fulfillment(trade_no: str):
    """异步通知 PSP 交付完成。"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{PSP_URL}/v1/trades/{trade_no}/fulfillment",
                json={"trade_no": trade_no},
            )
            if resp.status_code == 200:
                cprint(f"[ACT] PSP 交付确认成功: {trade_no}", DIM)
            else:
                cprint(f"[ACT] PSP 交付确认失败 ({resp.status_code}): {trade_no}", DIM)
    except Exception as e:
        cprint(f"[ACT] PSP 交付确认异常: {e}", DIM)


async def _execute_service_directly(
    task_id: str,
    skill_id: str,
    service_id: str,
    params: dict,
) -> dict:
    """直接执行服务（无需支付流程，用于测试或免费服务）。"""
    skill_result = await execute_skill(skill_id, params)

    artifact_id = f"artifact_{uuid.uuid4().hex[:16]}"
    payload = skill_result.get("payload", {})
    content_digest = compute_sha256_digest(payload)

    now_iso = to_iso(utc_now())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO artifacts
               (artifact_id, artifact_type, session_id, task_id,
                service_id, content_digest, payload, source_artifact_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                skill_result.get("artifact_type", "unknown"),
                f"a2a_session_{task_id}",
                task_id,
                service_id,
                content_digest,
                json.dumps(payload),
                json.dumps(skill_result.get("source_artifact_ids", [])),
                now_iso,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    await update_task_status(task_id, "FULFILLED")

    return {
        "status": "FULFILLED",
        "artifact": {
            "artifact_id": artifact_id,
            "artifact_type": skill_result.get("artifact_type"),
            "payload": payload,
            "service_id": service_id,
            "created_at": now_iso,
        },
    }
