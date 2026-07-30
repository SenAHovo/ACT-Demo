"""
旅游攻略生成技能 — 直接使用 Clawhub travel-assistant Prompt (By heidi1998)

服务 ID: lifestyle.travel.guide
价格: 0.35 CNY/次
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ============================================================
# 以下 Prompt 直接来自 Clawhub travel-assistant (By heidi1998)
# ============================================================
SYSTEM_PROMPT = """# 💡 角色定义
你叫做旅行助手，是一位专业的旅行规划师，细心周到，十分注重细节。

# 🎯 核心任务
- 专门帮用户把旅行准备做得滴水不漏，让用户能够专心享受旅程本身
- 主动发现和提醒用户可能忽略的细节——就像身边有一个跑过很多地方、心思无比缜密的朋友帮你把关
- 不只整理行程，更要提供一份让人安心的打包清单、签证等重要信息提醒
- 如果用户的提问不明确，就主动多问问题

# 📋 旅行检查清单
| 事项 | 参考提示 |
|------|---------|
| 检查护照 | 有效期至少剩余六个月；签证页是否足够 |
| 签证办理 | 提前查好受理时间与材料清单 |
| 重要文件 | 护照首页、机票酒店行程单、签证页的电子版存在手机和云端 |
| 当地天气 | 提前查好气温带对衣服 |
| 货币准备 | 本地货币是哪一种，大概换多少现金；信用卡在当地是否通用 |
| 手机漫游 | 提前开通国际漫游，或了解当地 Sim 卡怎么买 |
| 电压插头 | 确认当地电压与插头规格是否需要带转换器，如有必要准备排插 |
| 重要地址 | 预先存好酒店地址、接机方式、紧急联系人 |
| 使馆信息 | 目的地中国使领馆的地址与紧急求助电话 |
| 旅行保险 | 了解或购买短期旅行险 |
| 常用药品 | 感冒药、腹泻药、创可贴、晕车药等常备药 |
| 长途飞行舒适用品 | U型枕、眼罩、拖鞋、耳塞 |

## 🌟 安全提示
- 让用户了解当地治安情况，提醒危险区域
- 手机里存好当地报警、急救、火警电话

## 📝 格式要求
- 确保信息准确可靠。若涉及签证等重要信息，提示用户自行到官方网站确认最新政策
- 行程安排具体到每日上午、下午、晚上
- 使用清晰的标题分段
"""


def _get_llm():
    from llm.config import get_llm_config
    from llm.deepseek_adapter import DeepSeekAdapter
    config = get_llm_config("buyer")
    return DeepSeekAdapter(config)


def run(input_data: dict) -> dict:
    """
    执行旅游攻略生成。

    Args:
        input_data: {
            "destination_city": str,
            "departure_city": str,
            "days": int,
            "preferences": str (optional),
            "budget": str (optional),
        }
    """
    from shared.file_storage import save_file
    from shared.time_utils import utc_now, to_iso

    destination = input_data.get("destination_city", "")
    departure = input_data.get("departure_city", "")
    days = input_data.get("days", 3)
    preferences = input_data.get("preferences", "")
    budget = input_data.get("budget", "")

    if not destination:
        return {"success": False, "payload": {"error": "请提供目的地城市（destination_city）"}}
    if not departure:
        return {"success": False, "payload": {"error": "请提供出发地城市（departure_city）"}}
    try:
        days = int(days)
    except (ValueError, TypeError):
        days = 3

    pref_text = f"偏好: {preferences}" if preferences else ""
    budget_text = f"预算: {budget}" if budget else ""

    user_prompt = f"""请帮我规划一份旅行攻略。

出发地: {departure}
目的地: {destination}
游玩天数: {days} 天
{pref_text}
{budget_text}

请包含以下内容：
1. 出行方式汇总及建议（含时间、价格对比）
2. 城市基本信息（气候、最佳季节、市内交通）
3. 特色景点推荐（5-8个，含时长/门票）
4. 美食推荐（特色美食+推荐餐厅）
5. 文化与风俗
6. 历史背景
7. 每日详细日程规划
8. 行前准备清单（护照、签证、天气、货币、通讯、电器）
9. 安全与应急（治安、报警急救电话、使领馆联系方式）
10. 行李清单

请以结构化的方式输出，每个板块用 ## 标题分隔。"""

    llm = _get_llm()
    result = llm.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        temperature=0.8,
        max_tokens=6000,
    )
    content = result.strip()

    # 组装 Markdown 输出
    md_content = f"""# {destination} 旅游攻略

**{departure}出发 | {days}天游玩**

---

{content}

---

> 本攻略由 AI 智能体自动生成，信息仅供参考，出行前建议核实最新信息。
"""

    output_filename = f"{destination}旅游攻略_{days}天.md"
    new_file = save_file(
        filename=output_filename,
        content=md_content.encode("utf-8"),
        description=f"{departure}→{destination} {days}天旅游攻略",
        tags=["service-output", "travel-guide", "md"],
        source="system",
    )

    return {
        "success": True,
        "output_file_id": new_file["file_id"],
        "output_filename": output_filename,
        "payload": {
            "output_file_id": new_file["file_id"],
            "output_filename": output_filename,
            "destination": destination,
            "departure": departure,
            "days": days,
            "method": "clawhub-travel-assistant",
        },
    }
