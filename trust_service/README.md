# trust_service/ — 信任服务提供方

## 职责

DemoTrustService不是各域业务事实的唯一保存者。事件产生方负责生成、签名并保留原始记录，信任服务接收签名副本或摘要，提供集中索引、核验和追踪能力。运行端口：**8003**。

## 固定标识

```text
urn:demo:trust-service:local:v1
```

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 应用入口 | `app.py` | FastAPI应用，挂载存证、追踪、证据包等路由 |
| 事件注册表 | `event_registry.py` | 定义合法的ACT标准事件和demo命名空间事件类型 |
| 记录索引 | `record_index.py` | 保存签名事件副本或摘要，维护原始记录定位引用 |
| 验证器 | `verifier.py` | JCS规范化→SHA-256摘要→验签→核对引用和关联标识 |
| 追踪服务 | `trace_service.py` | 按delegation_id返回完整证据链 |
| 证据包服务 | `evidence_service.py` | 按trade_no或delegation_id导出证据包 |
| 锚点导出 | `anchor_exporter.py` | 生成待锚定摘要（不宣称完成ACT链上存证） |
| 数据库 | `database.py` | SQLite数据库定义 |

## ACT标准事件（使用act:命名空间）

```text
act:delegation:intent-created
act:delegation:delegation-issued
act:delegation:delegation-suspended
act:delegation:delegation-resumed
act:delegation:delegation-revoked
act:delegation:delegation-expired
act:commerce:decision-logged
act:payment:transaction-completed
act:commerce:fulfillment-completed
```

## Demo实现事件（使用demo:命名空间）

```text
demo:identity:authenticated
demo:payment:proof-verified
demo:task:completed
demo:attestation:submission-retried
```

## 异步存证规则

```text
业务事件完成 → 产生方本地保存原始签名记录 → 业务结果先返回 → 后台提交副本或摘要 → DemoTrustService索引并验签 → 失败进入产生方本地重试队列
```

存证失败不得将已经成功的支付或履约改为失败。

## 接口端点

```text
POST /v1/attestations
GET  /v1/attestations/{attestation_id}
GET  /v1/attestations
POST /v1/attestations/{attestation_id}/verify
GET  /v1/traces/{delegation_id}
GET  /v1/evidence-packages
POST /v1/anchors/export
```

## 不实现的能力

- ACT Trust Chain
- 链上锚点写入
- 多机构共识节点
- 正式争议裁决

## 数据表

```text
attestation_records
attestation_links
source_record_refs
verification_results
submission_retries
evidence_packages
```
