# 行业趋势分析 Skill

## 基本信息

- **Skill ID**: `industry-trend-analysis`
- **服务ID**: `analysis.industry.trend`
- **类别**: `analysis.industry`
- **价格**: 0.30 CNY
- **交付时间**: 即时（计算完成后）

## 输入

```json
{
  "source_artifact_id": "data_artifact_xxx",
  "source_digest": "sha256:...",
  "analysis_items": ["growth", "trend", "anomaly", "category_share"]
}
```

## 输出

```json
{
  "artifact_id": "analysis_artifact_xxx",
  "artifact_type": "industry_analysis",
  "source_artifact_ids": ["data_artifact_xxx"],
  "source_digests": ["sha256:..."],
  "content_digest": "sha256:...",
  "metrics": {},
  "trends": [],
  "anomalies": [],
  "evidence": []
}
```

## 目录结构

```text
industry-trend-analysis/
├── SKILL.md
├── scripts/
│   ├── validate_input.py       # 输入校验脚本
│   └── calculate_metrics.py    # 指标计算脚本
├── references/
│   ├── metric-definitions.md   # 指标定义
│   ├── analysis-rules.md       # 分析规则
│   └── output-schema.md        # 输出Schema
└── assets/
    └── analysis-template.json  # 分析模板
```

## 规则

- 数值计算**必须**由Python代码完成（`calculate_metrics.py`）
- 模型**不得**直接编造增长率、占比或异常点
- 模型**只可**解释已计算结果（通过卖方DeepSeek配置执行）
- 输入Artifact摘要必须匹配
- 输出必须引用输入Artifact
- 计算脚本必须具备单元测试
- 相同输入和配置应得到相同指标结果
