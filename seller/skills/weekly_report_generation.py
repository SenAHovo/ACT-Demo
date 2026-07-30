"""
周报生成技能 — 直接使用 Clawhub weekly-report-genius Prompt (By Kemi)

服务 ID: doc.weekly.report
价格: 0.30 CNY/次
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================
# 以下 Prompt 直接来自 Clawhub weekly-report-genius (By Kemi)
# ============================================================
SYSTEM_PROMPT = """你是一个周报生成器，你的职责是为用户生成一份专业、有条理的周报，帮助他们总结本周完成的工作，梳理遇到的问题，并规划下周计划。默认的情况下，你需要将周报的总标题设计为周报+本周范围，比如本周范围是7.21-7.25，周报标题即为「周报(7.21-7.25)」，下面可以有【本周进展】【存在问题】和【下周计划】三个部分。

## 核心流程
1. 请你先仔细阅读用户输入的内容，如果有模板文件，仔细理解模板的结构
2. 将用户输入的碎片化信息重新整理、润色为专业的周报语言
3. 对于仅包含一个要点的项目，使用一句话进行概括
4. 对于包含两个及以上的要点的项目，请先使用一句话概括，再逐条拆解要点内容，拆解时尽量使用学术化的项目符号，如积极、主动等，且每个要点都是提炼总结后再呈现的

## 语言润色规范 (极其重要！)
- 绝对不能讲大白话
- 必须将大白话转为书面化描述
- 请帮助用户将大白话转为更像是职场高手的书面化专业表达
- 必须用上专业的话术，比如：
  - "教会了新同事怎么用审批软件" 必须改为 "系统性的帮助团队成员提升了工具和技能"
  - "和产品经理讨论了一下系统审批的流程到底应该是怎么样" 必须改为 "就"审批系统流程"的主题，与产品经理进行了深入的探讨"
  - "对明年部门的目标有了一些想法" 必须改为 "初步思考并明确了部门目标"
  - "找财务部老张要了9月份的部门工资数据" 必须改为 "与财务部张老师就获取九月份部门工资数据进行了协调"
  - "修了一个用户提交订单后页面卡死的Bug" 必须改为 "完成了对用户反馈的"下单后页面卡死"的一个Bug，现已完成测试上线"
  - "对销售部的同事做了一次怎么使用新CRM系统的现场培训" 必须改为 "现场指导销售部同事学习使用新的CRM系统并提供使用建议"
  - "处理了几个客户投诉" 必须改为 "完成了对客户投诉的全面处理"
  - "把上个月的销售报表整理了一下" 必须改为 "完成了对上一月度销售数据的归集和汇总"

## 写作风格指南
- 必须积极正面，体现主人公是一位：效率高、高素质、能力强、专业、有主动探索精神和解决问题意愿的同事/下属
- 体现出主人公主动推进工作、积极协作的特质
- 如果有模板，严格遵循模板的格式和结构
- 不编造工作内容，只基于用户提供的进行润色

## 输出格式
请以 Markdown 格式输出，使用以下结构：

# 周报(日期范围)

## 本周进展
1. 概括第一项工作...
2. 概括第二项工作...

## 存在问题
1. 问题描述...

## 下周计划
1. 计划事项...
"""


def _get_llm():
    from llm.config import get_llm_config
    from llm.deepseek_adapter import DeepSeekAdapter
    config = get_llm_config("buyer")
    return DeepSeekAdapter(config)


def run(input_data: dict) -> dict:
    """
    执行周报生成。

    Args:
        input_data: {
            "template_file_id": str (optional),
            "work_items": [{"date": "...", "content": "..."}],
            "author": str (optional),
            "department": str (optional),
            "week_range": str (optional),
        }
    """
    from shared.file_storage import get_file, save_file
    from shared.time_utils import utc_now, to_iso

    template_file_id = input_data.get("template_file_id", "")
    work_items = input_data.get("work_items", [])
    author = input_data.get("author", "")
    department = input_data.get("department", "")
    week_range = input_data.get("week_range", "")

    # 构建工作内容描述
    work_text = "\n".join(
        f"- {w.get('date', '')}: {w.get('content', '')}" for w in work_items
    )

    if not work_text.strip():
        return {
            "success": False,
            "payload": {"error": "请提供本周工作内容（work_items）"},
        }

    user_prompt = f"""请帮我生成一份周报。

日期范围: {week_range or "本周"}
部门: {department or "未指定"}
报告人: {author or "未指定"}

本周工作内容:
{work_text}

请按照周报格式生成专业周报。"""

    llm = _get_llm()

    # 如果有模板，读取模板内容作为参考
    if template_file_id:
        finfo = get_file(template_file_id)
        if finfo:
            file_path = finfo["path"]
            if os.path.exists(file_path):
                if finfo.get("filename", "").lower().endswith(".docx"):
                    from docx import Document
                    doc = Document(file_path)
                    template_paras = [p.text for p in doc.paragraphs if p.text.strip()]
                    template_content = "\n".join(template_paras[:30])
                    user_prompt += f"\n\n模板格式参考（请遵循此格式结构）:\n{template_content}"
                else:
                    # 非 docx 模板，直接读文本
                    with open(file_path, "r", encoding="utf-8") as f:
                        template_content = f.read()[:3000]
                    user_prompt += f"\n\n模板格式参考:\n{template_content}"

    # 调用 LLM
    result = llm.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        temperature=0.7,
        max_tokens=4000,
    )
    content = result.strip()

    # 输出 Markdown
    output_filename = f"周报_{week_range or '本周'}.md"
    new_file = save_file(
        filename=output_filename,
        content=content.encode("utf-8"),
        description=f"周报 ({week_range or '本周'}, {len(work_items)}项工作)",
        tags=["service-output", "weekly-report", "md"],
        source="system",
    )

    return {
        "success": True,
        "output_file_id": new_file["file_id"],
        "output_filename": output_filename,
        "payload": {
            "output_file_id": new_file["file_id"],
            "output_filename": output_filename,
            "work_item_count": len(work_items),
            "method": "clawhub-weekly-report-genius",
        },
    }
