# 模拟行业数据查询 Skill

## 基本信息

- **Skill ID**: `industry-data-query`
- **服务ID**: `data.industry.query`
- **类别**: `data.industry`
- **价格**: 0.20 CNY
- **交付时间**: 即时

## 输入

```json
{
  "dataset_id": "retail-demo-2026",
  "start_month": "2026-01",
  "end_month": "2026-06",
  "dimensions": ["sales", "orders", "users", "category"]
}
```

## 输出

```json
{
  "artifact_id": "data_artifact_xxx",
  "artifact_type": "industry_data",
  "schema_version": "1.0",
  "content_digest": "sha256:...",
  "payload": {}
}
```

## 目录结构

```text
industry-data-query/
├── SKILL.md                    # 本文件
├── scripts/
│   └── query_dataset.py        # 数据查询脚本
├── references/
│   ├── dataset-schema.md       # 数据集Schema定义
│   └── service-rules.md        # 服务规则
└── assets/
    └── retail-demo-2026.json   # 模拟零售数据集
```

## 规则

- 不调用外部数据API
- 数据固定随仓库发布
- 输出可复现
- 数据文件只由卖方Skill读取
- 买方不能绕过服务接口访问资源
- 明确标注为模拟数据
