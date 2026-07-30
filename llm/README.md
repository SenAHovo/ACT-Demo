# llm/ — DeepSeek API适配层

## 职责

为买方智能体和卖方智能体中需要大模型参与的能力提供统一的DeepSeek API接入，支持全局配置和角色级覆盖。

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 配置管理 | `config.py` | 读取环境变量，管理全局和角色级DeepSeek配置 |
| 通用客户端 | `client.py` | LLM调用的统一接口封装 |
| DeepSeek适配器 | `deepseek_adapter.py` | DeepSeek API的具体适配实现 |

## 环境变量

### 全局配置（必填）

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
```

### 角色级覆盖（可选）

```env
BUYER_LLM_BASE_URL=
BUYER_LLM_API_KEY=
BUYER_LLM_MODEL=

SELLER_LLM_BASE_URL=
SELLER_LLM_API_KEY=
SELLER_LLM_MODEL=
```

## 配置优先级

```text
角色级配置 → 全局DeepSeek配置 → 启动失败并返回明确配置错误
```

## 模型使用范围

### 买方智能体中模型参与

- 自然语言意图解析
- 任务拆解建议
- 结果解释
- 报告生成

### 卖方智能体中模型参与

- 行业趋势解释（基于已计算结果）
- 报告内容生成（基于分析Artifact）

## 重要约束

- 大模型**不得**直接决定：IAC有效性、支付是否合规、预算是否超限、账户余额变化、凭证有效性、是否重复扣款、是否允许履约、存证验签结论
- 模型调用失败时，已经完成的支付、数据交付和存证记录**不得回滚**
- 模型调用失败**不得**导致重复购买上游服务
- 项目不提供无模型降级路径（无Mock模式）
