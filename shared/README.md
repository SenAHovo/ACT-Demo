# shared/ — 共享数据结构与工具

## 职责

为所有服务模块提供统一的数据模型定义、加解密工具、编码工具和通用错误码，确保跨服务的数据一致性和代码复用。

## 模块列表

| 模块 | 文件 | 职责 |
|---|---|---|
| 数据模型 | `schemas.py` | 所有核心数据对象的Pydantic模型定义（ISR/IAC/PaymentProof/Artifact等） |
| 身份工具 | `identity.py` | 身份标识生成、agent_id校验、身份方案验证 |
| 绑定工具 | `bindings.py` | UserAgentBinding和PaymentBinding的数据结构 |
| 交互信封 | `interaction.py` | InteractionEnvelope的模型定义和校验 |
| 签名工具 | `signatures.py` | Ed25519签名生成和验证 |
| 规范化 | `canonicalization.py` | RFC 8785 JCS（JSON Canonicalization Scheme）实现 |
| 编码工具 | `encoding.py` | Base64URL编解码 |
| 金额工具 | `money.py` | Decimal金额运算，确保两位小数，不使用float |
| 错误码 | `errors.py` | 统一错误码枚举（身份/授权/支付/存证等全部错误码） |
| 时间工具 | `time_utils.py` | ISO 8601 UTC时间格式化与校验 |

## 设计原则

- 所有金额使用 `Decimal` 或字符串，统一两位小数，**禁用float**
- JSON签名和摘要使用 RFC 8785 JCS 规范化
- 存证摘要使用 SHA-256
- 编码使用 Base64URL
- 时间使用 ISO 8601 UTC

## 核心数据对象

| 对象 | 说明 |
|---|---|
| AgentIdentityRecord | 智能体身份记录 |
| UserAgentBinding | 委托人—买方智能体绑定 |
| PaymentBinding | 支付方法绑定 |
| AuthenticationAssertion | 身份鉴别断言 |
| ISR | 意图结构化记录 |
| IAC | 意图授权凭证 |
| ServiceOffer | 商品化服务 |
| InteractionEnvelope | 交互信封 |
| ServiceInvocation | 服务调用 |
| PaymentNeeded | 支付要求头 |
| PaymentRequest | 支付请求 |
| PaymentProof | 支付凭证 |
| ServiceArtifact | 服务交付物 |
| AttestationRecord | 存证记录 |
| TaskBill | 任务账单 |
