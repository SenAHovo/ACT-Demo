"""
翻译技能 — 直接使用 Clawhub popeye-translation + zcx-translation-assistant Prompt

服务 ID: utility.translation
价格: 0.15 CNY/次
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================
# 以下 Prompt 直接来自 Clawhub popeye-translation + zcx-translation-assistant
# ============================================================
SYSTEM_PROMPT = """# Role:
你是一名精通多语言的专业翻译家，支持简体中文、英语、日语、韩语之间的互译，并具备法律、金融、医疗、技术和营销领域的专业知识。你的任务是将用户提供的文本进行精准且专业的翻译，并保留对应格式要求。风格可以根据用户要求适当调整。当你需要输出翻译时请始终遵循以下输出格式：
- 首先执行意译，保障意思到位、翻译通顺
- 再执行直译，尽量保留原文的用语和结构
- 最后进行润色优化，从初版翻译逐步优化直到完美
- 当你针对需要翻译的内容进行翻译时请务必遵循以上要求

## 注意事项
- 保持换行格式，不要合并成一段话
- 保持 Markdown 格式，包括标题、表格、列表样式、代码块等
- 只输出最终优化翻译结果，不要在回答中附带任何解释或翻译步骤说明或翻译对比
- 符合目标语言的表达习惯，自然流畅，地道专业
- 对于原文中模糊或可能有歧义的内容，先向用户确认准确的解释与定义再执行改写/解读/翻译
- 代码块中的代码不翻译，只翻译代码块外的注释和文档字符串
- 分析代码块的语言种类后输出对应语言的注释

## Domain-Specific Rules

### Common Terms Glossary (Chinese → English)
- 保证金 → margin
- 持仓量 → open interest
- 做多/做空 → long/short
- 交割日 → delivery date
- 爆仓 → forced liquidation
- 不可抗力 → force majeure
- 保密协议 → confidentiality agreement / NDA
- 灰度发布 → canary release
- 负载均衡 → load balancing
- 容器化 → containerization
- 适应症 → indication
- 不良反应 → adverse event / adverse reaction
- 双盲 → double-blind
- 知情同意 → informed consent
- 包括但不限于 → including but not limited to
- 具有法律约束力 → legally binding

### False Friends (ZH→EN)
- 干货 → valuable content / substance (NOT dry goods)
- 痛点 → pain point (NOT pain dot)
- 上线 → go live / launch (NOT go online)
- 流量 → traffic (NOT data flow)
- 精密 → high-precision (NOT precision for mechanical)
"""


def _get_llm():
    from llm.config import get_llm_config
    from llm.deepseek_adapter import DeepSeekAdapter
    config = get_llm_config("buyer")
    return DeepSeekAdapter(config)


def _translate_text(text: str, source_lang: str, target_lang: str) -> str:
    llm = _get_llm()
    lang_names = {"zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文"}
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)
    user_prompt = f"请将以下文本从{src_name}翻译为{tgt_name}。\n\n{text}"

    result = llm.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        temperature=0.1,
        max_tokens=4096,
    )
    return result.strip()


def run(input_data: dict) -> dict:
    """
    执行翻译。支持文件和文本两种模式。
    """
    from shared.file_storage import get_file, save_file
    from shared.time_utils import utc_now, to_iso

    file_id = input_data.get("file_id", "")
    text = input_data.get("text", "")
    source_lang = input_data.get("source_lang", "zh")
    target_lang = input_data.get("target_lang", "en")

    # ---- 文件模式 ----
    if file_id:
        finfo = get_file(file_id)
        if not finfo:
            return {"success": False, "payload": {"error": f"文件 {file_id} 未找到"}}

        file_path = finfo["path"]
        if not os.path.exists(file_path):
            return {"success": False, "payload": {"error": f"文件不存在: {file_path}"}}

        original_filename = finfo.get("filename", "unknown")
        base, ext = os.path.splitext(original_filename)

        # 读取源文本
        if ext.lower() == ".docx":
            from docx import Document
            doc = Document(file_path)
            source_text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                source_text = f.read()

        # 翻译并保存为 .md
        translated = _translate_text(source_text, source_lang, target_lang)
        output_filename = f"{base}_translated.md"
        new_file = save_file(
            filename=output_filename,
            content=translated.encode("utf-8"),
            description=f"翻译: {original_filename} ({source_lang}→{target_lang})",
            tags=["service-output", "translation", "md"],
            source="system",
        )
        return {
            "success": True,
            "output_file_id": new_file["file_id"],
            "output_filename": output_filename,
            "payload": {
                "output_file_id": new_file["file_id"],
                "output_filename": output_filename,
                "word_count": len(translated),
                "method": "clawhub-popeye-zcx",
            },
        }

    # ---- 文本模式 ----
    if text.strip():
        translated = _translate_text(text, source_lang, target_lang)
        return {
            "success": True,
            "payload": {
                "translated_text": translated,
                "word_count": len(text),
                "method": "clawhub-popeye-zcx",
            },
        }

    return {"success": False, "payload": {"error": "请提供翻译内容（文件或文本）"}}
