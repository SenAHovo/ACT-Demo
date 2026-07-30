# delegation_service/ — 委托授权、身份与绑定服务

## 职责

委托授权服务负责ISR（意图结构化记录）和IAC（意图授权凭证）的完整生命周期管理，同时内置最小身份与绑定能力，不新增独立进程。

运行端口：**8000**

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 应用入口 | `app.py` | FastAPI应用，挂载所有路由 |
| 身份注册表 | `identity_registry.py` | 维护买方/卖方/PSP/TrustService的本地身份记录 |
| 凭证管理器 | `credential_manager.py` | 为各参与方生成本地Ed25519凭证，维护有效/暂停/吊销/过期状态 |
| 认证服务 | `authentication_service.py` | 验证对方凭证，产生简化的AuthenticationAssertion |
| 用户-智能体绑定 | `user_agent_binding.py` | 维护委托人与买方智能体的绑定关系 |
| 支付绑定 | `payment_binding.py` | 建立买方智能体与模拟支付方法、模拟子账户的绑定 |
| 意图服务 | `intent_service.py` | 保存委托人确认后的ISR，生成intent_id |
| IAC签发器 | `issuer.py` | 根据ISR签发BOUNDED模式IAC，使用独立密钥签名 |
| 生命周期管理 | `lifecycle.py` | 管理Active/Suspended/Revoked/Expired状态转换 |
| 存证客户端 | `attestation_client.py` | 异步提交委托授权域存证事件 |
| 数据库 | `database.py` | SQLite数据库定义与连接管理 |

## 数据表

```text
agent_identities
agent_credentials
credential_status_history
user_agent_bindings
payment_bindings
authentication_assertions
intents
delegations
delegation_status_history
```
