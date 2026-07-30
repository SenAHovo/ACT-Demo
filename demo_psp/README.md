# demo_psp/ — 支付服务方

## 职责

DemoPSP是独立的支付服务方，负责核验买方身份、委托人-智能体绑定、支付绑定、IAC授权、预算额度、模拟子账户余额，执行模拟扣款并签发支付凭证。运行端口：**8002**。

## 固定标识

```text
psp_id  = urn:demo:psp:local:v1
method  = urn:demo:payment:local-balance:v1
```

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 应用入口 | `app.py` | FastAPI应用，挂载支付、查询、验证等路由 |
| 支付适配器接口 | `provider_adapter.py` | 统一支付接口（authorize/query/verify_proof/notify_fulfillment） |
| 本地余额适配器 | `adapters/local_balance.py` | LocalBalanceAdapter — 当前唯一支付实现，模拟余额扣款 |
| 账户服务 | `account_service.py` | 管理模拟子账户的余额、状态和余额变化记录 |
| 身份验证器 | `identity_verifier.py` | 验证买方本地凭证及状态 |
| IAC验证器 | `iac_verifier.py` | 验证IAC签名、生命周期、受托智能体、委托模式和有效期 |
| 绑定验证器 | `binding_verifier.py` | 验证user_agent_binding_id和payment_binding_id |
| 策略引擎 | `policy_engine.py` | 核验卖方、服务类别、支付方法、单笔和累计金额 |
| 支付处理器 | `payment_processor.py` | 按固定顺序执行14+步核验和扣款流程 |
| 凭证服务 | `proof_service.py` | 签发PaymentProof、验证凭证、检查重复使用 |
| 存证出箱 | `attestation_outbox.py` | 本地保存支付原始记录，异步提交存证副本 |
| 数据库 | `database.py` | SQLite数据库，管理账户、支付、凭证等 |

## 支付处理顺序

1. 校验请求标识 → 2. 校验时间戳 → 3. 验证买方凭证和签名 → 4. 验证委托人-买方绑定 → 5. 验证支付方法和子账户绑定 → 6. 验证IAC签名 → 7. 查询IAC状态 → 8. 核验受托智能体和BOUNDED模式 → 9. 核验支付方法/卖方/服务类别 → 10. 核验单笔和累计金额 → 11. 核验订单/资源/任务绑定 → 12. 核验模拟子账户 → 13. 幂等检查 → 14. 数据库事务扣款 → 15. 生成trade_no → 16. 写入支付记录 → 17. 签发支付凭证 → 18. 本地保存原始记录 → 19. 异步提交存证

## 接口端点

```text
GET  /schemas/local-balance-v1.json
GET  /v1/subaccounts/{sub_account_id}
POST /v1/payments
GET  /v1/payments/{out_trade_no}
POST /v1/payment-proofs/verify
POST /v1/trades/{trade_no}/fulfillment
```

## 交易状态

```text
CREATE → WAIT_BUYER_PAY → WAIT_SELLER_FULFILLMENT → TRADE_FINISHED / TRADE_CLOSED
```

## 数据表

```text
sub_accounts
payments
iac_usage
used_requests
payment_proofs
trade_status_history
attestation_outbox
```
