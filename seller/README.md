# seller/ — 卖方智能体

## 职责

卖方智能体代表同一商户或服务提供方，对外提供三项商品化服务（周报生成、旅游攻略生成、多语言翻译）。运行端口：**8001**。

## 固定标识

```text
agent_id = urn:demo:agent:seller:research-service-001
agent_id_scheme = demo
```

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 应用入口 | `app.py` | FastAPI应用，挂载Agent Card、服务目录、服务调用等路由 |
| 统一描述 | `canonical_agent_description.py` | 维护智能体统一描述，作为 Agent Card 和 GB/Z 描述的事实源 |
| Agent Card | `agent_card_serializer.py` | 将统一描述序列化为 Agent Card 格式（案例自定义） |
| 任务管理 | `a2a_task_manager.py` | 类 A2A 任务生命周期管理（案例内部协议） |
| GB/Z序列化器 | `gbz_description_serializer.py` | 将统一描述映射为GB/Z 185.4字段描述 |
| 服务目录 | `catalog.py` | 发布三项商品化服务，维护价格、类别和Schema |
| 认证适配器 | `authentication_adapter.py` | 验证买方凭证引用及状态 |
| 交互适配器 | `interaction_adapter.py` | 校验InteractionEnvelope，管理会话/任务/消息 |
| 商业控制器 | `commerce_controller.py` | 接收服务调用、生成订单、触发HTTP 402、验证支付凭证、激活Skill |
| 支付适配器 | `payment_adapter.py` | 发布支付能力声明、生成/解析支付头、调用DemoPSP验证凭证 |
| Skill注册表 | `skill_registry.py` | 建立service_id→Agent Skill→内部目录→Handler的映射 |
| 存证出箱 | `attestation_outbox.py` | 本地保存履约原始记录，异步提交存证副本 |

## Skill目录

```text
skills/
├── weekly-report-generation/    # 周报生成 (0.30元)
├── travel-guide-generation/     # 旅游攻略生成 (0.35元)
└── translation/                 # 多语言翻译 (0.15元)
```

每个Skill目录包含：
- `SKILL.md` — Skill能力描述
- `scripts/` — 确定性执行脚本
- `references/` — 参考文档（Schema、规则、格式）
- `assets/` — 静态数据与模板

## 接口端点

```text
GET  /.well-known/agent-card.json
GET  /.well-known/agent-description.json
GET  /.well-known/act-payment-capability.json
GET  /v1/catalog
GET  /v1/catalog/{service_id}
POST /v1/sessions/authenticate
POST /v1/services/{service_id}/invoke
GET  /v1/tasks/{task_id}
GET  /v1/orders/{out_trade_no}
```

## 数据表

```text
service_catalog
sessions
service_tasks
service_messages
service_invocations
seller_orders
artifacts
proof_usage
attestation_outbox
```
