# buyer/ — 买方智能体

## 职责

买方智能体是委托任务的执行主体，接收委托人的自然语言任务，在授权边界内自主发现服务、做出购买决策、发起支付并汇总结果。

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 主控制器 | `agent.py` | 买方智能体入口，编排整体执行流程 |
| 意图解析器 | `intent_parser.py` | 解析委托人自然语言任务，生成ISR草稿，通过DeepSeek执行意图解析 |
| 任务规划器 | `planner.py` | 拆解子任务、建立依赖、计算预计成本、确定执行顺序 |
| 身份客户端 | `identity_client.py` | 读取本地买方凭证和绑定信息 |
| 认证客户端 | `authentication_client.py` | 与卖方建立本地已鉴别会话，生成session_id |
| 发现客户端 | `discovery_client.py` | 通过预配置入口获取卖方Agent Card和服务目录 |
| 交互客户端 | `interaction_client.py` | 封装InteractionEnvelope，管理买卖双方消息交互 |
| 策略引擎 | `policy_engine.py` | 每笔交易前确定性检查：IAC状态、卖方范围、金额、服务类别等 |
| 支付客户端 | `payment_client.py` | 解析Payment-Needed、构造支付请求、调用DemoPSP、保存PaymentProof |
| 制品存储 | `artifact_store.py` | 保存DataArtifact、AnalysisArtifact和ReportArtifact及来源关系 |
| 任务账本 | `task_ledger.py` | 记录task/session/intent/delegation_id、子任务状态、支付流水和总支出 |
| 存证出箱 | `attestation_outbox.py` | 本地保存原始签名记录，异步提交存证副本到DemoTrustService |

## 固定标识

```text
agent_id = urn:demo:agent:buyer:001
agent_id_scheme = demo
```
