# seller/skills/ — Skill实现目录

## 说明

三个Skill均在卖方智能体内部执行，通过Skill Registry建立 service_id → Agent Skill → 内部Skill目录 → Handler 的映射。不通过独立工具服务对外发布，因此不构成GB/Z 185.7工具调用实现。

## 关键概念区分

| 概念 | 说明 | 位置 |
|---|---|---|
| A2A Agent Skill | Agent Card中的公开能力描述 | `/.well-known/agent-card.json` |
| 内部Skill目录 | 卖方智能体内部按需加载的实现包 | `skills/` 目录 |
| 商品化服务 (Service Offer) | 带价格和交付条件的交易标的 | `GET /v1/catalog` |

## 三项服务

| Skill | service_id | category | 价格 |
|---|---|---|---|
| 模拟行业数据查询 | `data.industry.query` | `data.industry` | 0.20 CNY |
| 行业趋势分析 | `analysis.industry.trend` | `analysis.industry` | 0.30 CNY |
| 简要行业报告生成 | `report.industry.brief` | `report.industry` | 0.40 CNY |

总支出 0.90元，处于 1.00元 预算内。

## 每个Skill目录结构

```text
skill-name/
├── SKILL.md          # Skill能力描述
├── scripts/          # 确定性执行脚本
├── references/       # 参考文档（Schema、规则、格式）
└── assets/           # 静态数据与模板
```
