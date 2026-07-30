# 简要行业报告生成 Skill

## 基本信息

- **Skill ID**: `industry-report-generation`
- **服务ID**: `report.industry.brief`
- **类别**: `report.industry`
- **价格**: 0.40 CNY
- **交付时间**: 取决于模型响应时间

## 输入

```json
{
  "source_artifact_id": "analysis_artifact_xxx",
  "source_digest": "sha256:...",
  "report_language": "zh-CN",
  "report_length": "brief"
}
```

## 输出

```json
{
  "artifact_id": "report_artifact_xxx",
  "artifact_type": "industry_report",
  "source_artifact_ids": ["analysis_artifact_xxx"],
  "source_digests": ["sha256:..."],
  "content_digest": "sha256:...",
  "title": "模拟零售行业趋势简报",
  "content": "...",
  "generated_by": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash"
  }
}
```

## 目录结构

```text
industry-report-generation/
├── SKILL.md
├── scripts/
│   ├── validate_analysis.py    # 分析结果校验脚本
│   └── build_report_prompt.py  # Prompt构建脚本
├── references/
│   ├── report-structure.md     # 报告结构规范
│   ├── evidence-rules.md       # 证据引用规则
│   └── style-guide.md          # 写作风格指南
└── assets/
    ├── brief-report-template.md # 简要报告模板
    └── report-schema.json       # 报告输出Schema
```

## 规则

- 报告**只能**依据输入分析Artifact
- **不得**引入未提供的数据结论
- 重要数值**必须**追溯到 `metrics` 或 `evidence`
- 报告生成通过卖方DeepSeek配置执行
- 默认继承全局 `deepseek-v4-flash` 模型
- 允许通过卖方角色级配置覆盖模型
- DeepSeek调用失败**不得**重复购买上游服务
- 输出必须记录实际使用的模型标识
- 报告生成失败与支付成功**分开**记录
