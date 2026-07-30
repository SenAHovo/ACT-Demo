"""
对话式购买智能体 — 基于 LLM Function Calling（流式彩色输出版）

用户通过自然语言对话与买方智能体交互。
支持：
  - 流式 LLM 输出（边思考边显示）
  - 彩色控制台输出（思考/工具/支付/结果各不同颜色）
  - Artifact 数据链路（上游服务输出自动传入下游）
  - 购买完成后展示实际数据内容
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv; load_dotenv()

from llm.config import get_llm_config
from llm.deepseek_adapter import DeepSeekAdapter
from buyer.database import init_db
from buyer.discovery_client import discover_seller
from buyer.authentication_client import authenticate_with_seller
from buyer.a2a_client import (
    discover_services,
    create_a2a_task,
    send_task_message,
    pay_and_fulfill_task,
)
from buyer.task_ledger import record_task, update_task, get_total_spent
from shared.file_storage import save_service_result, list_files, get_file, get_file_text, save_upload, delete_file
from shared.console_colors import cprint, cwrite, CYAN, YELLOW, GREEN, MAGENTA, RED, DIM, RESET, BOLD

import httpx

DELEGATION_URL = os.getenv("DELEGATION_SERVICE_URL", "http://127.0.0.1:8000")
PSP_URL = os.getenv("PSP_URL", "http://127.0.0.1:8002")
SELLER_URL = os.getenv("SELLER_URL", "http://127.0.0.1:8001")
BUYER_ID = "urn:demo:agent:buyer:001"
SELLER_ID = "urn:demo:agent:seller:research-service-001"


# ============================================================
# 安全打印
# ============================================================
def _safe_print(text: str, color: str = RESET):
    try:
        cprint(text, color)
    except UnicodeEncodeError:
        cprint(text.encode("gbk", errors="replace").decode("gbk"), color)


def _safe_write(text: str, color: str = RESET):
    try:
        cwrite(text, color)
    except UnicodeEncodeError:
        cwrite(text.encode("gbk", errors="replace").decode("gbk"), color)


def _clean_emoji(text: str) -> str:
    """移除或替换 Windows GBK 控制台无法显示的字符。"""
    try:
        text.encode("gbk")
        return text
    except UnicodeEncodeError:
        return text.encode("gbk", errors="replace").decode("gbk")


# ============================================================
# System Prompt
# ============================================================
SYSTEM_PROMPT = """你是「ACT 智能体自主委托支付 Demo」中的 AI 购买助手。

你的核心职责是通过 Agent-to-Agent 任务协议帮助用户发现和购买各类智能体服务（周报生成、旅游攻略生成、翻译等）。

## ACT 四大域流程
1. 委托授权域: confirm_purchase_plan → create_delegation（签发 IAC，设定预算上限）
2. 商业交互域: 在卖家智能体上创建 Task → 发送 Message → 卖家 Skill 执行
3. 支付结算域: 卖家返回 PAYMENT_REQUIRED → 执行 PSP 支付 → 卖家完成交付
4. 信任服务域: 卖家自动提交存证，保障不可否认性

## 自我介绍
向用户介绍自己时，始终称自己为「AI 购买助手」。

## 输出格式（重要！）
- 始终使用纯文本，禁止使用任何 Markdown 格式
- 禁止使用：加粗(**)、表格(|)、代码块(```)、标题(#)、列表(-)
- 服务列表用 "1. xxx" 编号即可
- 价格直接写数字，无需特殊格式

## 行为准则
1. 意图识别：先判断用户是否真想购买服务
   - 闲聊/打招呼 → 友好回复，不调购买工具
   - 问"能做什么" → 介绍能力，不主动调发现工具
   - "看看有什么"/"帮我买" → 购买意图，开始调工具
2. 服务筛选：用户表达明确意图时（如"我要生成周报"），调用 discover_services 时传入 intent 参数，
   让系统自动筛选相关服务，**只向用户展示匹配的服务，不要列出所有服务**。
   用户说"看看有什么"等无明确意图时才列出全部。
3. 委托授权确认：创建委托(IAC)时系统会弹出确认卡片，用户点击确认后才签发授权。confirm_purchase_plan 是静默步骤，不弹卡片
4. 金额透明：告知价格，汇报支出
5. 简明扼要：中文回复，尽量简练

## 关键规则：预充值账户模式
- 用户的支付账户已预充值，余额充足，直接购买即可
- 发现服务后，先调用 check_balance 查看实际账户余额
- 使用账户余额作为预算上限（调用 confirm_purchase_plan 时传入当前余额）
- 无需计算 "1.2倍缓冲"——账户余额就是上限，花多少扣多少
- 向用户展示：各服务价格 + 当前账户余额
- 在 confirm_purchase_plan 被调用前，绝对不得调用 create_delegation
- 每次购买前后，调用 check_balance 查看余额变化
- 购买完成后告知用户剩余余额

## 服务说明
- 周报生成（doc.weekly.report, 0.30 CNY）：需要工作内容列表（work_items），可选择性上传模板文件，输出 MD 文档
- 旅游攻略（lifestyle.travel.guide, 0.35 CNY）：需要目的地、出发地、天数信息，可选偏好和预算
- 多语言翻译（utility.translation, 0.15 CNY）：可上传文件（DOCX/TXT/MD）或直接发文本，输出 MD 文件或文本

## 重要
- 周报生成需要提供工作内容（work_items），没有内容无法生成
- 翻译服务需要用户上传文件（传 file_id）或在对话中发送要翻译的文本（传 text），二选一
- 如果服务需要前置条件（文件/参数），必须提醒用户满足后再调用 purchase_service

## 可用工具
- discover_services: 通过 A2A Agent Card 发现可用服务。用户有明确意图（如"生成周报"）时传入 intent 参数筛选相关服务；用户无明确意图（如"看看有什么"）时不传 intent，列出全部服务
- check_balance: 查看当前预算限额和已用/剩余金额
- confirm_purchase_plan: 确认购买计划和预算上限 — 必须在 create_delegation 之前调用
- create_delegation: 创建委托授权(IAC) — 必须在 confirm_purchase_plan 之后调用
- purchase_service: 通过 A2A Task/Message 协议购买服务。一次调用一项
- show_summary: 展示任务汇总(已完成服务、支出)

## 流程
1. 用户表达购买意图 → discover_services（传入 intent 筛选相关服务）
2. 展示相关服务 + 价格 → check_balance 告知用户账户余额
3. 调用 confirm_purchase_plan 设定预算和要买的服务（静默执行，不弹卡片）→ create_delegation（系统会弹出委托授权卡片，展示完整购买计划，等待用户确认后签发 IAC）
4. 逐项 purchase_service（A2A: 创建 Task → 发送 Message → 支付 → 获取交付物）
5. 过程中可随时 check_balance 查看余额
6. show_summary"""

TOOLS = [
    {"type": "function", "function": {"name": "discover_services", "description": "发现可用数据服务。用户有明确意图时传入intent筛选相关服务；用户说「看看有什么」时不传intent列出全部。", "parameters": {"type": "object", "properties": {"intent": {"type": "string", "description": "用户的购买意图/需求描述，用于筛选相关服务。如「生成周报」「翻译文件」「旅游攻略」。无明确意图时不传。"}}, "required": []}}},
    {"type": "function", "function": {"name": "check_balance", "description": "查看 PSP 账户余额、当前预算上限、已用金额和剩余可用余额。购买前后可调用。", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "confirm_purchase_plan", "description": "确认购买计划和预算上限。先调用 check_balance 获取余额，然后传入余额作为 budget_limit。必须在 create_delegation 之前调用。", "parameters": {"type": "object", "properties": {"budget_limit": {"type": "string", "description": "预算上限金额(CNY)，传入 check_balance 返回的当前余额"}, "service_ids": {"type": "array", "items": {"type": "string"}, "description": "计划购买的服务 ID 列表"}}, "required": ["budget_limit", "service_ids"]}}},
    {"type": "function", "function": {"name": "create_delegation", "description": "创建委托授权(IAC)。必须在 confirm_purchase_plan 确认通过后调用。", "parameters": {"type": "object", "properties": {"task_goal": {"type": "string", "description": "任务目标"}}, "required": ["task_goal"]}}},
    {"type": "function", "function": {"name": "purchase_service", "description": "购买指定服务。旅游攻略传destination_city/departure_city/days；周报传work_items(工作内容数组[{date,content}])，模板可选传file_id；翻译：上传了文件传file_id，直接发文本传text，可选source_lang/target_lang。", "parameters": {"type": "object", "properties": {"service_id": {"type": "string", "description": "服务ID: doc.weekly.report / lifestyle.travel.guide / utility.translation"}, "destination_city": {"type": "string", "description": "[旅游攻略] 目的地城市"}, "departure_city": {"type": "string", "description": "[旅游攻略] 出发地城市"}, "days": {"type": "integer", "description": "[旅游攻略] 游玩天数"}, "preferences": {"type": "string", "description": "[旅游攻略] 偏好(可选)"}, "budget_level": {"type": "string", "description": "[旅游攻略] 预算级别(可选)"}, "file_id": {"type": "string", "description": "[翻译/周报] 用户上传的文件ID，翻译传文件ID，周报传模板文件ID(可选)"}, "text": {"type": "string", "description": "[翻译] 要翻译的文本（仅当用户直接在对话中发送文本时使用，与file_id二选一）"}, "source_lang": {"type": "string", "description": "[翻译] 源语言(可选)，默认zh"}, "target_lang": {"type": "string", "description": "[翻译] 目标语言(可选)，默认en"}, "work_items": {"type": "array", "items": {"type": "object", "properties": {"date": {"type": "string"}, "content": {"type": "string"}}}, "description": "[周报] 工作内容列表，必填"}, "author": {"type": "string", "description": "[周报] 报告人(可选)"}, "department": {"type": "string", "description": "[周报] 部门(可选)"}, "week_range": {"type": "string", "description": "[周报] 周范围如'7.21-7.25'(可选)"}, "language_style": {"type": "string", "description": "[周报] 语言风格(可选)，默认'business'"}}, "required": ["service_id"]}}},
    {"type": "function", "function": {"name": "show_summary", "description": "展示任务汇总(已完成服务、支出)", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "no_action", "description": "用户无购买意图(闲聊用)", "parameters": {"type": "object", "properties": {"response": {"type": "string"}}, "required": ["response"]}}},
]


# ============================================================
# 对话智能体
# ============================================================
class ConversationAgent:

    def __init__(self):
        config = get_llm_config("buyer")
        self._llm = DeepSeekAdapter(config)
        self._messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._session_id: str | None = None
        self._delegation: dict | None = None
        self._credential_id: str | None = None
        self._services_cache: list[dict] = []
        # Artifact 数据链：购买后存储最新 artifact，传给下游服务
        self._last_artifact: dict | None = None
        self._purchased_artifacts: list[dict] = []
        # 最近一次购买产生的文件元数据（供 chat_stream 检测 file_ready）
        self._last_file_meta: dict | None = None
        # 本轮对话中用户上传的文件 ID 列表
        self._pending_file_ids: list[str] = []
        # 购买计划确认状态（预算、服务列表）
        self._confirmed_plan: dict | None = None
        # A2A 交互步骤（供 chat_stream 逐条展示）
        self._a2a_steps: list[str] = []
        # 委托授权确认机制
        self._delegation_event: asyncio.Event | None = None
        self._delegation_confirmed: bool = False

    # ============================================================
    # 工具实现
    # ============================================================
    # 服务关键词映射 — 用于匹配用户意图与相关服务
    SERVICE_KEYWORDS = {
        "doc.weekly.report": ["周报", "汇报", "日报", "总结", "报告", "工作", "周", "报", "weekly", "report"],
        "lifestyle.travel.guide": ["旅游", "旅行", "攻略", "游玩", "景点", "出行", "度假", "travel", "guide", "旅"],
        "utility.translation": ["翻译", "译", "英文", "中文", "语言", "translate", "translation", "翻"],
    }

    # 服务使用说明 — 告诉用户怎么用
    SERVICE_USAGE = {
        "doc.weekly.report": "使用方式：提供工作内容（work_items），每项含日期和内容，可选上传模板文件",
        "lifestyle.travel.guide": "使用方式：提供目的地、出发地、游玩天数，可选偏好和预算",
        "utility.translation": "使用方式：上传文件（DOCX/TXT/MD）或直接发送文本，可选源语言和目标语言",
    }

    def _match_services(self, intent: str, services: list[dict]) -> list[dict]:
        """根据用户意图进行关键词匹配，返回按相关度排序的服务列表。"""
        if not intent or not intent.strip():
            return services  # 无意图时返回全部

        intent_lower = intent.lower()
        # 中文按字符切分（补充空格分词不足以处理无空格中文的问题）
        tokens = set(intent_lower.split())
        for ch in intent:
            if '\u4e00' <= ch <= '\u9fff':  # CJK 字符单独加入 token
                tokens.add(ch)

        scored = []
        for svc in services:
            sid = svc.get("service_id", "")
            keywords = self.SERVICE_KEYWORDS.get(sid, [])
            # 计算匹配分数：关键词命中数
            score = sum(1 for kw in keywords if kw.lower() in intent_lower)

            # 额外加分：服务名称、分类、描述中的词/token 命中
            combined_text = " ".join([
                svc.get("name", ""),
                svc.get("category", ""),
                svc.get("description", ""),
            ]).lower()
            for token in tokens:
                if len(token) >= 1 and token in combined_text:
                    score += 0.5
            scored.append((score, svc))

        # 按分数降序排列
        scored.sort(key=lambda x: x[0], reverse=True)

        # 筛选：有匹配分的服务，或如果全都没匹配则返回全部
        matched = [svc for score, svc in scored if score > 0]
        return matched if matched else services

    async def _tool_discover_services(self, intent: str = "") -> str:
        """发现服务：根据用户意图筛选相关服务，列出简要说明和使用方式。"""
        card = await discover_seller()
        services = await discover_services()
        self._services_cache = services

        # 根据意图筛选相关服务
        relevant = self._match_services(intent, services)

        lines = [f"卖方: {card.get('name', '未知')}"]
        if intent:
            lines.append(f"根据「{intent}」为您匹配到 {len(relevant)} 项相关服务:")
        else:
            lines.append(f"提供 {len(relevant)} 项服务:")

        total = 0.0
        for i, svc in enumerate(relevant, 1):
            price = float(svc.get("price", 0))
            total += price
            lines.append(f"  {i}. {svc['name']}（{svc['service_id']}）")
            lines.append(f"     价格: {svc['price']} {svc.get('currency', 'CNY')}")
            lines.append(f"     简介: {svc.get('description', '')}")

        if not intent:
            lines.append(f"合计: {total:.2f} CNY")
        return "\n".join(lines)

    async def _tool_confirm_purchase_plan(self, args: dict) -> str:
        """确认购买计划：设定预算上限，验证预算是否足够。"""
        budget_limit_str = args.get("budget_limit", args.get("budget", "0"))
        service_ids = args.get("service_ids", [])

        try:
            budget_limit = float(budget_limit_str)
        except ValueError:
            return f"错误: 预算上限格式不正确: '{budget_limit_str}'，请使用纯数字如 1.20"

        if budget_limit <= 0:
            return "错误: 预算上限必须大于 0。"

        if not service_ids:
            return "错误: 请指定要购买的服务列表。"

        # 确保已发现服务
        if not self._services_cache:
            self._services_cache = await discover_services()

        # 计算所选服务总价
        selected_services = []
        total = 0.0
        for sid in service_ids:
            match = None
            for svc in self._services_cache:
                if svc.get("service_id") == sid or svc.get("id") == sid:
                    match = svc
                    break
            if match:
                price = float(match.get("price", 0))
                total += price
                selected_services.append(match)
            else:
                return f"错误: 未找到服务 {sid}。可用服务: {[s.get('service_id','') for s in self._services_cache]}"

        if total > budget_limit:
            return (
                f"预算不足！所选服务总价 {total:.2f} CNY，超出预算上限 {budget_limit:.2f} CNY。\n"
                f"请减少服务或提高预算上限。"
            )

        # 存储确认的计划（预算上限模式）
        self._confirmed_plan = {
            "budget_limit": budget_limit,
            "service_ids": service_ids,
            "total_price": total,
            "spent": 0.0,
            "purchased": [],
        }

        return (
            f"计划确认!\n"
            f"预算上限: {budget_limit:.2f} CNY\n"
            f"服务总价: {total:.2f} CNY\n"
            f"剩余可用: {(budget_limit - 0):.2f} CNY\n"
            f"服务列表: {', '.join(service_ids)}\n"
            f"现在可以调用 create_delegation 创建委托。"
        )

    async def _tool_create_delegation(self, args: dict) -> str:
        # 安全闸：必须先通过 confirm_purchase_plan
        if not self._confirmed_plan:
            return (
                "错误: 尚未确认购买计划。请先调用 confirm_purchase_plan。\n"
                "流程: discover_services → confirm_purchase_plan → create_delegation"
            )
        if not self._confirmed_plan.get("service_ids"):
            return "错误: 购买计划中没有选择任何服务。请先调用 confirm_purchase_plan。"

        task_goal = args.get("task_goal", "")
        max_amount = str(self._confirmed_plan.get("budget_limit", "1.00"))

        cprint(f"    goal: {task_goal}, budget_limit: {max_amount} CNY", DIM)

        if not self._session_id:
            self._session_id = await authenticate_with_seller()
            cprint(f"    session: {self._session_id}", DIM)

        async with httpx.AsyncClient(timeout=10.0) as client:
            intent_resp = await client.post(f"{DELEGATION_URL}/v1/intents", json={
                "task_goal": task_goal, "agent_id": BUYER_ID,
                "user_agent_binding_id": "uab_demo_001",
                "max_total_amount": max_amount, "max_single_amount": max_amount,
                "allowed_sellers": [SELLER_ID],
                "allowed_categories": ["utility", "document.office", "lifestyle.travel"],
                "allowed_payment_methods": ["urn:demo:payment:local-balance:v1"],
            })
            if intent_resp.status_code != 200:
                detail = intent_resp.json().get("detail", intent_resp.text)
                return f"创建意图失败 (HTTP {intent_resp.status_code}): {detail}"

            intent = intent_resp.json()
            del_resp = await client.post(f"{DELEGATION_URL}/v1/delegations", json={"intent_id": intent["intent_id"]})
            if del_resp.status_code != 200:
                detail = del_resp.json().get("detail", del_resp.text)
                return f"签发委托失败 (HTTP {del_resp.status_code}): {detail}"

            self._delegation = del_resp.json()
            identity_resp = await client.get(f"{DELEGATION_URL}/v1/identities/{BUYER_ID}")
            if identity_resp.status_code != 200:
                detail = identity_resp.json().get("detail", identity_resp.text)
                return f"获取身份失败 (HTTP {identity_resp.status_code}): {detail}"
            self._credential_id = identity_resp.json()["credential_id"]

        return f"IAC: {self._delegation['delegation_id']}\n预算上限: {max_amount} CNY"

    async def _tool_check_balance(self) -> str:
        """查看账户余额。"""
        import httpx
        # 尝试查询 PSP 账户余额
        psp_balance = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{PSP_URL}/v1/subaccounts/subacct_buyer_001")
                if resp.status_code == 200:
                    data = resp.json()
                    psp_balance = data.get("balance", "?")
        except Exception:
            pass

        if not self._confirmed_plan:
            if psp_balance:
                return f"账户余额: {psp_balance} CNY\n尚未设定购买计划。请先发现服务并确认。"
            return "尚未设定预算。请先发现服务并确认购买计划。"

        limit = self._confirmed_plan.get("budget_limit", 0)
        spent = self._confirmed_plan.get("spent", 0.0)
        remaining = limit - spent
        purchased = self._confirmed_plan.get("purchased", [])

        lines = []
        if psp_balance:
            lines.append(f"[PSP] 账户余额: {psp_balance} CNY")
        lines.append(f"预算上限: {limit:.2f} CNY")
        lines.append(f"已花费: {spent:.2f} CNY")
        lines.append(f"剩余可用: {remaining:.2f} CNY")
        lines.append(f"已购买: {len(purchased)} 项 ({', '.join(purchased) if purchased else '无'})")
        return "\n".join(lines)

    async def _tool_purchase_service(self, args: dict) -> str:
        """
        A2A 购买流程：
        0. 前置检查（翻译需文件、预算余额）
        1. 在卖家智能体上创建 A2A Task
        2. 发送任务消息（委托凭证 + 自然语言描述服务需求）
        3. 卖家 LLM 解析意图并回复确认
        4. 如果卖家返回 PAYMENT_REQUIRED → 执行支付 → 触发履约
        5. 获取 Artifact → 保存文件 → 更新余额
        """
        service_id = args.get("service_id", "")
        if not self._delegation or not self._session_id or not self._credential_id:
            return "错误: 请先创建委托授权（先 discover_services → confirm_purchase_plan → create_delegation）"

        # ---- 查服务名称和价格 ----
        svc_name = service_id
        svc_price = "?"
        for svc in self._services_cache:
            if svc.get("service_id") == service_id or svc.get("id") == service_id:
                svc_name = svc.get("name", service_id)
                svc_price = svc.get("price", "?")
                break

        # ---- 前置检查 1: 翻译服务需要文件或文本 ----
        user_text = args.get("text", "")
        user_file_id = args.get("file_id", "")
        if service_id == "utility.translation" and not self._pending_file_ids and not user_file_id and not user_text.strip():
            return (
                f"错误: 翻译服务需要用户提供要翻译的内容！\n"
                f"请告诉用户：可以上传文档（支持 DOCX/TXT/MD/JSON/CSV），或者在对话中直接发送要翻译的文本。"
            )

        # ---- 前置检查 2: 预算余额 ----
        if self._confirmed_plan:
            remaining = self._confirmed_plan.get("budget_limit", 0) - self._confirmed_plan.get("spent", 0.0)
            price = float(svc_price) if svc_price != "?" else 0
            if price > remaining:
                return (
                    f"余额不足！{svc_name} 价格 {price:.2f} CNY，但剩余可用只有 {remaining:.2f} CNY。\n"
                    f"请告知用户余额不足，建议提高预算或调整购买计划。"
                )
            # 检查是否已购买过
            purchased = self._confirmed_plan.get("purchased", [])
            if service_id in purchased:
                return (
                    f"该服务 {service_id} 已经购买过了。"
                    f"如需重新购买请先重置系统。"
                )

        # ---- 构造服务输入参数 ----
        input_data: dict = {}
        if service_id == "doc.weekly.report":
            work_items = args.get("work_items", [])
            if not work_items:
                return (
                    f"错误: 周报生成需要工作内容（work_items）！\n"
                    f"请告诉用户：需要提供工作内容列表，每项包含 date 和 content。"
                )
            report_file_id = user_file_id or (self._pending_file_ids[0] if self._pending_file_ids else "")
            input_data = {
                "work_items": work_items,
                "author": args.get("author", ""),
                "department": args.get("department", ""),
                "week_range": args.get("week_range", ""),
                "language_style": args.get("language_style", "business"),
            }
            if report_file_id:
                input_data["template_file_id"] = report_file_id
        elif service_id == "lifestyle.travel.guide":
            destination = args.get("destination_city", "")
            departure = args.get("departure_city", "")
            days = args.get("days", 3)
            if not destination:
                return "错误: 旅游攻略需要目的地城市（destination_city），请从用户消息中提取。"
            if not departure:
                return "错误: 旅游攻略需要出发地城市（departure_city），请从用户消息中提取。"
            input_data = {
                "destination_city": destination,
                "departure_city": departure,
                "days": days,
                "preferences": args.get("preferences", ""),
                "budget": args.get("budget_level", ""),
            }
        elif service_id == "utility.translation":
            lang_src = args.get("source_lang", "zh")
            lang_tgt = args.get("target_lang", "en")
            if self._pending_file_ids:
                from shared.file_storage import get_file as get_fs_file
                finfo = get_fs_file(self._pending_file_ids[0])
                fname = finfo.get("filename", "未知文件") if finfo else "未知文件"
                input_data = {"file_id": self._pending_file_ids[0], "source_lang": lang_src, "target_lang": lang_tgt}
            elif user_file_id:
                from shared.file_storage import get_file as get_fs_file
                finfo = get_fs_file(user_file_id)
                fname = finfo.get("filename", "未知文件") if finfo else "未知文件"
                input_data = {"file_id": user_file_id, "source_lang": lang_src, "target_lang": lang_tgt}
            elif user_text.strip():
                fname = ""
                input_data = {"text": user_text.strip(), "source_lang": lang_src, "target_lang": lang_tgt}
            else:
                fname = ""
                input_data = {"text": "", "source_lang": lang_src, "target_lang": lang_tgt}
        elif self._last_artifact:
            input_data["source_artifact"] = self._last_artifact.get("payload", self._last_artifact)
            input_data["source_artifact_id"] = self._last_artifact.get("artifact_id", "")

        # ---- 映射 service_id → skill_id ----
        SERVICE_TO_SKILL = {
            "doc.weekly.report": "weekly-report-generation",
            "lifestyle.travel.guide": "travel-guide-generation",
            "utility.translation": "translation",
        }
        skill_id = SERVICE_TO_SKILL.get(service_id, service_id)

        # ---- 构造自然语言消息（让卖家 LLM 理解意图） ----
        if service_id == "doc.weekly.report":
            from shared.file_storage import get_file as get_fs_file
            report_file_id = user_file_id or (self._pending_file_ids[0] if self._pending_file_ids else "")
            finfo = get_fs_file(report_file_id) if report_file_id else None
            template_name = finfo.get("filename", "模板") if finfo else "周报模板"
            work_items = input_data.get("work_items", [])
            work_text = "; ".join(f"{w.get('date','')}: {w.get('content','')}" for w in work_items)
            author = input_data.get("author", "")
            dept = input_data.get("department", "")
            week = input_data.get("week_range", "")
            style = input_data.get("language_style", "business")
            extra_info = ""
            if author: extra_info += f"\n报告人: {author}"
            if dept: extra_info += f"\n部门: {dept}"
            if week: extra_info += f"\n周范围: {week}"
            message_content = (
                f"你好，我需要生成一份周报。\n"
                f"语言风格: {style}\n"
                f"工作内容: {work_text}"
                f"{extra_info}\n"
                f"委托ID: {self._delegation['delegation_id']}"
            )
            if report_file_id:
                # 拼接模板信息在消息末尾
                message_content = (
                    f"你好，我需要生成一份周报。\n"
                    f"模板文件: {template_name}\n"
                    f"模板文件ID: {report_file_id}\n"
                    f"语言风格: {style}\n"
                    f"工作内容: {work_text}"
                    f"{extra_info}\n"
                    f"委托ID: {self._delegation['delegation_id']}"
                )
        elif service_id == "lifestyle.travel.guide":
            dest = input_data.get("destination_city", "")
            dep = input_data.get("departure_city", "")
            days = input_data.get("days", 3)
            prefs = input_data.get("preferences", "")
            budget = input_data.get("budget", "")
            extra = ""
            if prefs: extra += f"\n偏好: {prefs}"
            if budget: extra += f"\n预算: {budget}"
            message_content = (
                f"你好，我需要一份旅游攻略。\n"
                f"目的地: {dest}\n"
                f"出发地: {dep}\n"
                f"游玩天数: {days} 天"
                f"{extra}\n"
                f"委托ID: {self._delegation['delegation_id']}"
            )
        elif service_id == "utility.translation":
            from shared.file_storage import get_file as get_fs_file
            lang_name = {"zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文"}
            lang_s = lang_name.get(lang_src, lang_src)
            lang_t = lang_name.get(lang_tgt, lang_tgt)
            report_file_id = user_file_id or (self._pending_file_ids[0] if self._pending_file_ids else "")
            if self._pending_file_ids or user_file_id:
                if not fname and report_file_id:
                    finfo = get_fs_file(report_file_id)
                    fname = finfo.get("filename", "未知文件") if finfo else "未知文件"
                message_content = (
                    f"你好，我需要翻译一份文件。\n"
                    f"文件名: {fname}\n"
                    f"文件ID: {report_file_id}\n"
                    f"从{lang_s}翻译到{lang_t}，请帮我处理。\n"
                    f"委托ID: {self._delegation['delegation_id']}"
                )
            else:
                text_preview = user_text[:150] + ("..." if len(user_text) > 150 else "")
                message_content = (
                    f"你好，我需要翻译一段文本。\n"
                    f"原文: {text_preview}\n"
                    f"从{lang_s}翻译到{lang_t}，请帮我处理。\n"
                    f"委托ID: {self._delegation['delegation_id']}"
                )
        else:
            message_content = (
                f"请执行服务: {svc_name}\n"
                f"参数: {json.dumps(input_data, ensure_ascii=False)}\n"
                f"委托ID: {self._delegation['delegation_id']}"
            )

        # ---- 1. 创建 A2A Task ----
        delegation_id = self._delegation["delegation_id"]
        self._a2a_steps = []  # 本轮的 A2A 步骤
        self._a2a_steps.append(f"[买家] 创建 A2A 任务 (goal: {svc_name})")
        task = await create_a2a_task(
            goal=f"购买服务: {svc_name}",
            delegation_id=delegation_id,
        )
        task_id = task["task_id"]
        self._a2a_steps.append(f"[买家] 任务已创建: {task_id}")

        # 记录任务到账本（初始状态 PENDING）
        price_str = svc_price if svc_price != "?" else "0"
        await record_task(task_id, self._session_id or "", service_id, delegation_id, price_str)

        # ---- 2. 发送任务消息给卖家 ----
        self._a2a_steps.append(f"[买家→卖家] 发送服务请求...")
        result = await send_task_message(
            task_id=task_id,
            content=message_content,
            sender_role="buyer_agent",
        )

        # ---- 3. 解析卖家回复 ----
        seller_response = result.get("response_text", "")
        task_result = result.get("result", {})

        # 优先使用卖家 LLM 解析出的 skill_id（更准确）
        seller_skill_id = result.get("skill_id", "") or task_result.get("skill_id", "")
        if seller_skill_id:
            skill_id = seller_skill_id

        if seller_response:
            self._a2a_steps.append(f"[卖家→买家] {seller_response}")

        # ---- 验证卖家返回的 service_id 是否与请求一致 ----
        seller_service_id = task_result.get("service_id", "")
        if seller_service_id and seller_service_id != service_id:
            self._a2a_steps.append(f"[警告] 卖家返回了不同服务: {seller_service_id}（请求的是 {service_id}）")
            return (
                f"A2A 服务不匹配: 请求 {service_id}（{svc_name}），"
                f"但卖家返回了 {seller_service_id}。请重新尝试。"
            )

        # ---- 4. 处理支付 ----
        if task_result.get("status") == "PAYMENT_REQUIRED":
            payment_needed_raw = task_result.get("payment_needed", {})
            payment_needed = payment_needed_raw.get("payment_needed", payment_needed_raw)
            amount = payment_needed.get("amount", "?")
            self._a2a_steps.append(f"[卖家] 要求支付: {amount} CNY")
            cprint(f"    >>> A2A: 需支付 {amount} CNY", YELLOW)

            # 执行支付
            self._a2a_steps.append(f"[买家] 执行 PSP 支付...")
            fulfill = await pay_and_fulfill_task(
                task_id=task_id,
                service_id=service_id,
                skill_id=skill_id,
                input_data=input_data,
                payment_needed=payment_needed,
                delegation=self._delegation,
                session_id=self._session_id,
                credential_id=self._credential_id,
            )
            if fulfill.get("status") != "FULFILLED":
                self._a2a_steps.append(f"[错误] 支付或履约失败")
                return f"A2A 履约失败: {fulfill.get('error', '未知错误')}"

            artifact = fulfill.get("artifact", {})
            self._a2a_steps.append(f"[卖家] 服务交付完成")
            cprint(f"    >>> A2A: 服务已交付", GREEN)

            # 更新账本为已完成
            trade_no = fulfill.get("trade_no", "")
            await update_task(task_id, trade_no, str(payment_needed.get("amount", 0)), "COMPLETED")

        elif task_result.get("status") == "FULFILLED":
            artifact = task_result.get("artifact", {})
            cprint(f"    >>> A2A: 直接交付", GREEN)
            # 无支付路径也记录为完成
            await update_task(task_id, "", str(payment_needed.get("amount", 0)), "COMPLETED")
        else:
            return f"A2A 任务状态异常: {task_result.get('status', 'UNKNOWN')}"

        # ---- 5. 处理 Artifact ----
        self._last_artifact = artifact
        self._purchased_artifacts.append(artifact)

        # 保存文件
        file_meta = save_service_result(service_id, artifact, "")
        self._last_file_meta = file_meta

        # ---- 更新余额 ----
        price = float(svc_price) if svc_price != "?" else 0
        if self._confirmed_plan:
            self._confirmed_plan["spent"] = self._confirmed_plan.get("spent", 0.0) + price
            self._confirmed_plan["purchased"] = self._confirmed_plan.get("purchased", []) + [service_id]
        remaining = (self._confirmed_plan.get("budget_limit", 0) - self._confirmed_plan.get("spent", 0.0)) if self._confirmed_plan else 0

        # ---- 格式化输出（展示买卖双方交互过程） ----
        lines = []
        lines.append(f"[买家→卖家] 创建 A2A 任务: {task_id}")
        lines.append(f"[买家→卖家] 发送消息: {message_content[:200]}")

        if seller_response:
            lines.append(f"[卖家→买家] {seller_response}")

        if task_result.get("status") == "PAYMENT_REQUIRED":
            lines.append(f"[卖家] 要求支付: {amount} CNY")
            lines.append(f"[买家] 执行 PSP 支付... 完成")

        lines.append(f"[卖家] 服务交付完成")

        # 文件产出
        if file_meta:
            lines.append(f"[产出] {file_meta['filename']} (可下载)")

        # 余额
        if self._confirmed_plan:
            lines.append(f"[余额] 已花费 {self._confirmed_plan['spent']:.2f} / 上限 {self._confirmed_plan['budget_limit']:.2f} CNY (剩余 {remaining:.2f})")

        # 数据预览
        data_section = self._format_artifact_data(service_id, artifact)
        if data_section.strip():
            lines.append(data_section)

        return "\n".join(lines)

    def _format_artifact_data(self, service_id: str, artifact: dict) -> str:
        """格式化 artifact 数据为可读文本。"""
        payload = artifact.get("payload", {})
        if not payload:
            return "  (无数据)"

        lines = []
        if service_id == "doc.weekly.report":
            lines.append(f"  周报已生成，风格: {payload.get('language_style', 'business')}，内容项: {payload.get('work_item_count', 0)} 项")

        elif service_id == "lifestyle.travel.guide":
            lines.append(f"  攻略已生成: {payload.get('departure', '')}→{payload.get('destination', '')}，{payload.get('days', '?')}天")
            lines.append(f"  板块: {', '.join(payload.get('sections', []))}")

        elif service_id == "utility.translation":
            lines.append("  --- 翻译结果 ---")
            out_fid = payload.get("output_file_id")
            if out_fid:
                # 文件模式
                lines.append(f"  原文文件: {payload.get('original_filename', '?')}")
                lines.append(f"  输出文件: {payload.get('output_filename', '?')}")
                preview = payload.get("translated_preview", "")
                if preview:
                    lines.append(f"  内容预览: {preview[:200]}")
                lines.append(f"  翻译方式: {payload.get('method', '?')}")
            else:
                # 文本模式
                lines.append(f"  原文语言: {payload.get('source_lang', '?')}")
                lines.append(f"  目标语言: {payload.get('target_lang', '?')}")
                lines.append(f"  译文: {payload.get('translated_text', '')}")
                lines.append(f"  置信度: {payload.get('confidence', '?')}")

        return "\n".join(lines)

    async def _tool_show_summary(self) -> str:
        if not self._delegation:
            return "暂无进行中的任务"
        total = await get_total_spent(self._delegation["delegation_id"], self._session_id or "")
        lines = [f"IAC: {self._delegation['delegation_id']}", f"总支出: {total} CNY"]
        if self._confirmed_plan:
            budget_limit = self._confirmed_plan.get("budget_limit", 0)
            spent = self._confirmed_plan.get("spent", 0.0)
            lines.append(f"预算上限: {budget_limit:.2f} CNY / 已花费: {spent:.2f} CNY / 剩余: {(budget_limit - spent):.2f} CNY")
        for a in self._purchased_artifacts:
            svc = a.get("service_id", "?")
            adata = a.get("payload", {})
            lines.append(f"  [{svc}] {a.get('artifact_id','')}")
        return "\n".join(lines)

    async def _tool_no_action(self, args: dict) -> str:
        return args.get("response", "好的。")

    # ---- 委托授权确认（供 Web GUI 调用） ----
    def confirm_delegation(self):
        """用户确认委托授权。"""
        self._delegation_confirmed = True
        if self._delegation_event:
            self._delegation_event.set()

    def cancel_delegation(self):
        """用户取消委托授权。"""
        self._delegation_confirmed = False
        if self._delegation_event:
            self._delegation_event.set()

    async def _execute_tool(self, tool_call: dict) -> str:
        name = tool_call["function"]["name"]
        try:
            args = json.loads(tool_call["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}

        # 打印工具调用
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 80:
            args_str = args_str[:77] + "..."
        cprint(f"  [工具] {name}({args_str})", YELLOW)

        handler = {
            "discover_services": lambda: self._tool_discover_services(args.get("intent", "")),
            "check_balance": lambda: self._tool_check_balance(),
            "confirm_purchase_plan": lambda: self._tool_confirm_purchase_plan(args),
            "create_delegation": lambda: self._tool_create_delegation(args),
            "purchase_service": lambda: self._tool_purchase_service(args),
            "show_summary": lambda: self._tool_show_summary(),
            "no_action": lambda: self._tool_no_action(args),
        }.get(name)

        if handler is None:
            result = f"未知工具: {name}"
        else:
            try:
                result = await handler()
            except Exception as e:
                result = f"异常: {type(e).__name__}: {e}"

        cprint(f"  [结果] {result}", GREEN)
        return result

    # ============================================================
    # 流式对话
    # ============================================================
    async def initialize(self):
        await init_db()
        print("买方智能体初始化完成\n")

    async def chat(self, user_input: str) -> str:
        """处理一轮用户输入（流式输出，支持思考模式）。"""
        self._messages.append({"role": "user", "content": user_input})

        max_rounds = 10
        for _ in range(max_rounds):
            cwrite("  [思考] ", CYAN)
            stream = self._llm.chat_with_tools_stream(self._messages, tools=TOOLS, temperature=0.3)

            reasoning_parts: list[str] = []  # 思维链
            content_parts: list[str] = []    # 输出文本
            all_tool_calls: list[dict] = []

            for chunk in stream:
                if chunk["type"] == "reasoning":
                    reasoning_parts.append(chunk["text"])
                    _safe_write(chunk["text"], DIM)  # 思维链用暗色
                elif chunk["type"] == "content":
                    content_parts.append(chunk["text"])
                    _safe_write(chunk["text"], RESET)
                elif chunk["type"] == "tool_calls":
                    all_tool_calls = chunk["tool_calls"]
                elif chunk["type"] == "done":
                    pass

            print()  # 换行

            round_text = "".join(content_parts).strip()
            round_reasoning = "".join(reasoning_parts).strip()

            if all_tool_calls:
                # 构建 assistant 消息（工具调用轮次必须包含 reasoning_content）
                asst_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": round_text or None,
                    "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in all_tool_calls],
                }
                if round_reasoning:
                    asst_msg["reasoning_content"] = round_reasoning
                self._messages.append(asst_msg)

                for tc in all_tool_calls:
                    result = await self._execute_tool(tc)
                    self._messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                continue
            else:
                # 纯文本回复（无需 reasoning_content，API 会忽略）
                text = round_text
                self._messages.append({"role": "assistant", "content": text})
                return _clean_emoji(text)

        return "处理超时，请简化请求重试。"

    async def run_loop(self):
        await self.initialize()
        cprint("=" * 60, CYAN)
        cprint("  ACT 对话式购买智能体", BOLD)
        cprint("  输入退出: quit / exit", DIM)
        cprint("=" * 60, CYAN)
        print()
        _safe_print("助手: 你好！我是AI购买助手。试试说「帮我看看有什么数据服务可以买」。")

        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "退出"):
                print("再见！")
                break

            print()
            response = await self.chat(user_input)
            print()
            _safe_print(f"助手: {response}", RESET)

    # ============================================================
    # Web GUI 流式对话方法 (SSE)
    # ============================================================
    async def chat_stream(self, user_input: str, file_ids: list[str] | None = None):
        """流式处理用户输入，生成 SSE 事件流。用于 Web GUI。

        SSE 事件:
          connected   — 连接确认
          thinking    — 模型思维链内容（展示在思考面板）
          chat        — 对话文本（展示在对话区）
          tool_start  — 开始调用工具
          tool_result — 工具执行结果
          a2a         — A2A 买卖双方交互步骤（逐条展示）
          file_ready  — 服务产出了可下载文件
          done        — 本轮对话完成
          error       — 错误

        标准模型（如 deepseek-v4-flash）开启思考模式后也会产生 reasoning_content。

        Yields:
            str: SSE 事件字符串
        """
        import json as _json

        def _sse(event: str, data: str | dict) -> str:
            payload = _json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else data
            return f"event: {event}\ndata: {payload}\n\n"

        # ==== 处理已上传文件 ====
        self._pending_file_ids = file_ids or []
        user_content = user_input
        if self._pending_file_ids:
            file_infos = []
            for fid in self._pending_file_ids:
                ftext = get_file_text(fid)
                finfo = get_file(fid)
                if ftext and finfo:
                    file_infos.append(
                        f"[用户上传文件 file_id={fid} 文件名={finfo.get('filename','')} "
                        f"内容长度={len(ftext)} 字符]\n{ftext[:4000]}"
                    )
            if file_infos:
                user_content = (
                    "用户上传了以下文件:\n" + "\n\n".join(file_infos)
                    + "\n\n用户消息: " + user_input
                )

        self._messages.append({"role": "user", "content": user_content})

        yield ": ok\n\n"
        yield _sse("connected", {"text": ""})

        max_rounds = 10
        all_round_texts: list[str] = []  # 累积多轮输出文本，最终一起发给 done

        for _round in range(max_rounds):
            stream = self._llm.chat_with_tools_stream(self._messages, tools=TOOLS, temperature=0.3)

            reasoning_parts: list[str] = []  # 推理链内容（仅推理模型）
            content_parts: list[str] = []    # 输出文本
            all_tool_calls: list[dict] = []

            for chunk in stream:
                if chunk["type"] == "reasoning":
                    # 推理模型专用：思考链逐 token 展示到思考面板
                    reasoning_parts.append(chunk["text"])
                    yield _sse("thinking", {"text": chunk["text"]})
                elif chunk["type"] == "content":
                    # 标准模型：输出文本仅累积，不流式发送
                    content_parts.append(chunk["text"])
                elif chunk["type"] == "tool_calls":
                    all_tool_calls = chunk["tool_calls"]
                elif chunk["type"] == "done":
                    pass

            round_text = "".join(content_parts).strip()

            if all_tool_calls:
                if round_text:
                    all_round_texts.append(round_text)
                    # 每轮工具调用前，先把这轮说的话发到对话面板
                    yield _sse("chat", {"text": round_text})

                yield _sse("tool_start", {"tools": [tc["function"]["name"] for tc in all_tool_calls]})

                # 构建 assistant 消息（工具调用轮次必须包含 reasoning_content）
                asst_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": round_text or None,
                    "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in all_tool_calls],
                }
                if reasoning_parts:
                    asst_msg["reasoning_content"] = "".join(reasoning_parts)
                self._messages.append(asst_msg)

                for tc in all_tool_calls:
                    if tc["function"]["name"] == "create_delegation":
                        # ---- 拦截：发送委托授权卡片，展示完整购买计划 + 等待用户确认 ----
                        tc_args = _json.loads(tc["function"]["arguments"])
                        task_goal = tc_args.get("task_goal", "")
                        budget_limit = str(self._confirmed_plan.get("budget_limit", "")) if self._confirmed_plan else ""
                        total_price = str(self._confirmed_plan.get("total_price", "")) if self._confirmed_plan else ""
                        svc_ids = self._confirmed_plan.get("service_ids", []) if self._confirmed_plan else []

                        # 查找服务名称和价格
                        svc_details = []
                        for sid in svc_ids:
                            svc_info = next((s for s in self._services_cache if s.get("service_id") == sid), None)
                            if svc_info:
                                svc_details.append({
                                    "service_id": sid,
                                    "name": svc_info.get("name", sid),
                                    "price": f"{svc_info.get('price', '?')} {svc_info.get('currency', 'CNY')}",
                                })
                            else:
                                svc_details.append({"service_id": sid, "name": sid, "price": "?"})

                        # 获取当前账户余额
                        balance_str = "?"
                        try:
                            async with httpx.AsyncClient(timeout=5.0) as client:
                                resp = await client.get(f"{PSP_URL}/v1/subaccounts/subacct_buyer_001")
                                if resp.status_code == 200:
                                    bal_data = resp.json()
                                    balance_str = f"{bal_data.get('balance', '?')} CNY"
                        except Exception:
                            pass

                        yield _sse("delegation_pending", {
                            "task_goal": task_goal,
                            "budget_limit": budget_limit,
                            "total_price": total_price,
                            "balance": balance_str,
                            "services": svc_details,
                        })

                        # 等待用户在 GUI 上确认/取消
                        self._delegation_event = asyncio.Event()
                        self._delegation_confirmed = False
                        try:
                            await asyncio.wait_for(self._delegation_event.wait(), timeout=120.0)
                        except asyncio.TimeoutError:
                            result = "委托授权超时（120秒），已自动取消。"
                            yield _sse("delegation_resolved", {"confirmed": False})
                            yield _sse("tool_result", {"tool": "create_delegation", "result": result})
                            self._messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                            self._delegation_event = None
                            continue

                        self._delegation_event = None

                        if not self._delegation_confirmed:
                            result = "用户取消了委托授权。"
                            yield _sse("delegation_resolved", {"confirmed": False})
                            yield _sse("tool_result", {"tool": "create_delegation", "result": result})
                            self._messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                            continue

                        # 用户确认了，通知前端移除卡片
                        yield _sse("delegation_resolved", {"confirmed": True})

                    result = await self._execute_tool(tc)
                    yield _sse("tool_result", {
                        "tool": tc["function"]["name"],
                        "result": result,
                    })
                    self._messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

                    # ---- A2A 交互步骤：逐条展示 ----
                    if tc["function"]["name"] == "purchase_service" and self._a2a_steps:
                        for step in self._a2a_steps:
                            yield _sse("a2a", {"step": step})
                        self._a2a_steps = []

                    if tc["function"]["name"] == "purchase_service" and self._last_file_meta:
                        try:
                            tc_args = _json.loads(tc["function"]["arguments"])
                            svc_id = tc_args.get("service_id", "")
                        except _json.JSONDecodeError:
                            svc_id = ""
                        yield _sse("file_ready", {
                            "file_id": self._last_file_meta["file_id"],
                            "filename": self._last_file_meta["filename"],
                            "service_id": svc_id,
                        })
                        self._last_file_meta = None

                self._pending_file_ids = []
                continue
            else:
                # 最终轮（无工具调用）：先发 chat，再发 done
                if round_text:
                    all_round_texts.append(round_text)
                    yield _sse("chat", {"text": round_text})
                full_response = "\n\n".join(all_round_texts)
                self._messages.append({"role": "assistant", "content": full_response})
                yield _sse("done", {"text": full_response})
                return

        yield _sse("error", {"text": "处理超时，请简化请求重试。"})

    # ============================================================
    # 文件管理方法（供 Web GUI 调用）
    # ============================================================
    def get_files(self, source: str | None = None) -> list[dict]:
        """获取文件列表。"""
        files = list_files(source=source)
        return [
            {
                "file_id": f["file_id"],
                "filename": f["filename"],
                "size": f["size"],
                "description": f["description"],
                "source": f["source"],
                "created_at": f["created_at"],
                "content_type": f["content_type"],
            }
            for f in files
        ]

    def get_file_info(self, file_id: str) -> dict | None:
        """获取文件信息。"""
        return get_file(file_id)

    def read_file(self, file_id: str) -> str | None:
        """读取文本文件内容。"""
        return get_file_text(file_id)

    def upload_file(self, file_data: bytes, filename: str) -> dict:
        """保存用户上传的文件。"""
        return save_upload(file_data, filename)

    def remove_file(self, file_id: str) -> bool:
        """删除文件。"""
        return delete_file(file_id)
