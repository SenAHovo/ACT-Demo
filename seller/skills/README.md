# seller/skills/ — Skill实现目录

## 说明

三个Skill均在卖方智能体内部执行，通过Skill Registry建立 service_id → Agent Skill → 内部Skill目录 → Handler 的映射。不通过独立工具服务对外发布，因此不构成GB/Z 185.7工具调用实现。

## 关键概念区分

| 概念 | 说明 | 位置 |
|---|---|---|
| Agent Skill | Agent Card 中的公开能力描述 | `/.well-known/agent-card.json` |
| 内部Skill目录 | 卖方智能体内部按需加载的实现包 | `skills/` 目录 |
| 商品化服务 (Service Offer) | 带价格和交付条件的交易标的 | `GET /v1/catalog` |

## 三项服务

| Skill | service_id | category | 价格 |
|---|---|---|---|
| 周报生成 | `doc.weekly.report` | `document.office` | 0.30 CNY |
| 旅游攻略生成 | `lifestyle.travel.guide` | `lifestyle.travel` | 0.35 CNY |
| 多语言翻译 | `utility.translation` | `utility` | 0.15 CNY |

总支出 0.80元，处于 1.00元 预算内。

## 每个Skill目录结构

```text
skill-name/
├── SKILL.md          # Skill能力描述
├── scripts/          # 确定性执行脚本
├── references/       # 参考文档（Schema、规则、格式）
└── assets/           # 静态数据与模板
```
