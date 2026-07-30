# ACT 智能体自主委托支付 Demo — 系统审计与书稿素材报告

> 生成日期：2026-07-29  
> 用途：书稿撰写素材 — 系统架构、ACT 合规性、适用性评估

---

## 一、系统概述

本 Demo 是一个**端到端的智能体自主委托支付教学案例**，完整演示了 ACT（Agentic Commerce Trust Protocol）协议的四层架构在实际场景中的运作方式。

**业务场景**：委托人（用户）通过对话式 Web 界面，委托买方智能体去发现、购买卖方智能体提供的付费服务（周报生成、旅游攻略、翻译），全程由 ACT 协议保障身份可信、委托可控、支付可追溯、存证不可否认。

### 核心数据流

```
用户(Web GUI) ─→ 买方智能体(buyer) ─→ 委托授权服务(delegation, :8000)
                    │                        ├── 签发 Ed25519 密钥对
                    │                        ├── 创建 ISR（意图结构化记录）
                    │                        └── 签发 IAC（带 Ed25519 签名）
                    │
                    ├──→ 卖方智能体(seller, :8001)
                    │    ├── Agent Card 发现 (.well-known/agent-card.json)
                    │    ├── 服务目录 (v1/catalog)
                    │    ├── A2A Task/Message 协议
                    │    ├── HTTP 402 Payment-Needed
                    │    └── Skill 执行与 Artifact 交付
                    │
                    ├──→ 支付服务方(demo_psp, :8002)
                    │    ├── 19 步支付验证流水线
                    │    ├── Ed25519 签名支付凭证
                    │    └── 异步存证出箱
                    │
                    └──→ 信任服务(trust_service, :8003)
                         ├── 存证记录存储
                         ├── SHA-256 哈希验证
                         ├── 证据链追踪 (trace)
                         └── 证据包导出
```

---

## 二、系统架构

### 2.1 整体拓扑

系统由 **5 个独立服务 + 1 个 Web GUI** 组成，全部通过 multiprocessing 并行启动：

| 组件 | 端口 | 核心职责 |
|------|------|----------|
| **delegation_service** | 8000 | 身份管理、凭证签发、ISR/IAC 生成、Ed25519 签名 |
| **seller** | 8001 | Agent Card 暴露、服务目录、A2A 协议、Skill 执行 |
| **demo_psp** | 8002 | 19 步支付验证、扣款、支付凭证签发、存证 |
| **trust_service** | 8003 | 存证记录索引、SHA-256 验证、证据链追踪 |
| **web_gui** | 8080 | SSE 流式对话界面、委托授权交互卡片、文件上传 |
| **buyer** | (嵌入) | LLM Function Calling 驱动的对话智能体 |

### 2.2 各模块详解

#### 2.2.1 买方智能体（buyer/）

- **conversation_agent.py**（约 800 行）：核心对话引擎
  - 基于 DeepSeek API 的 Function Calling，将工具调用映射到 ACT 流程
  - 实现关键词匹配的服务筛选（`_match_services`）
  - 管理完整的购买生命周期：发现 → 预算确认 → 委托授权(弹卡片) → A2A 购买 → 汇总
  - 人工介入机制：委托授权时弹出确认/取消卡片（asyncio.Event 阻塞等待）
  - SSE 流式输出，支持 interactive_card 事件类型

- **a2a_client.py**：A2A 商业交互客户端
  - 创建 A2A Task → 发送 Message → 处理 402 支付 → 履约交付

- **payment_client.py / agent.py**：支付客户端和非交互式自动购买

#### 2.2.2 委托授权服务（delegation_service/）

- **issuer.py**：IAC 签发器
  - 持有独立 Ed25519 密钥对（买方不持有私钥）
  - 对 IAC 载荷进行 JCS 规范化 + Ed25519 签名
  - 签发后异步提交存证到信任服务

- **app.py**：17 个 REST API 端点
  - 身份注册、凭证管理、认证验证
  - 用户-智能体绑定、支付绑定
  - ISR 创建、IAC 签发、生命周期管理（暂停/恢复/吊销）
  - 公钥暴露端点 `GET /v1/public-key`（供 PSP 验证 IAC 签名）

- **credential_manager.py**：为每个参与方生成 Ed25519 密钥对

- **intent_service.py**：创建意图结构化记录（ISR）

- **lifecycle.py**：IAC 状态管理（Active/Suspended/Revoked/Expired）

#### 2.2.3 卖方智能体（seller/）

- **app.py**：22 个 REST API 端点
  - Agent Card 暴露（`.well-known/agent-card.json`）
  - 服务目录（`v1/catalog`）
  - 服务调用（`v1/services/{id}/invoke`）— 支持 402 支付拦截
  - A2A 协议端点：Task CRUD、Message 发送、支付回调

- **commerce_controller.py**：服务调用核心逻辑
  - 未支付 → 生成订单 + 返回 HTTP 402 Payment-Needed
  - 已支付 → 验证凭证（含 Ed25519 签名校验 + amount/seller_id 匹配）→ 执行 Skill

- **a2a_message_handler.py**：A2A 消息处理，含 LLM 意图解析

- **payment_adapter.py**：支付凭证独立验证
  - 验证 proof 中的 seller_id 必须匹配
  - 验证 proof 中的 amount 必须匹配服务价格
  - 防止 proof 重复使用（proof_usage 表）

- **skills/ 目录**：三项 Skill 实现
  - `weekly_report_generation.py`：LLM 生成周报 MD 文档
  - `travel_guide_generation.py`：LLM 生成旅游攻略 MD 文档
  - `translation.py`：支持 DOCX/TXT/MD 文件翻译和文本翻译

#### 2.2.4 支付服务方（demo_psp/）

- **payment_processor.py**（约 340 行）：**19 步支付验证流水线**
  1. 校验请求标识
  2. 校验时间戳（5 分钟窗口）
  3. 验证买方凭证归属
  4. 验证委托人-买方绑定
  5. 验证支付绑定
  6. 获取 IAC 并验证 Ed25519 签名
  7. 交叉验证 IAC 的 user_agent_binding_id
  8. 校验受托智能体和 BOUNDED 模式
  9. 策略核验：卖方、类别、支付方法白名单
  10. 单笔限额检查
  11. 累计限额检查（从 iac_usage 表汇总）
  12. 资源校验
  13. 子账户检查
  14. 幂等检查（request_id + SHA-256 摘要）
  15. 执行扣款
  16. 写入支付记录
  17. 签发 Ed25519 签名支付凭证（PaymentProof）
  18. 本地保存原始记录
  19. 返回结果

- **iac_verifier.py**：IAC 验证
  - 从委托授权服务拉取 Ed25519 公钥（带缓存）
  - 验证 IAC 载荷的 Ed25519 签名（防篡改）
  - 检查状态、有效期、受托智能体、委托模式

- **proof_service.py**：支付凭证验证
  - Ed25519 签名验证（PSP 签名）
  - 状态检查、过期检查
  - 关键字段匹配（resource_id、seller_id、buyer_agent_id、amount 等）

- **policy_engine.py**：策略引擎
  - 单笔限额、累计限额、卖方白名单、类别白名单、支付方法白名单

- **attestation_outbox.py**：异步存证出箱
  - 包含完整上下文（delegation_id、task_id、trade_no、participants）
  - Ed25519 签名的存证记录
  - 30 秒定时批量提交

#### 2.2.5 信任服务（trust_service/）

- **app.py**：8 个 API 端点
  - 存证存储（POST /v1/attestations）
  - 存证查询（GET /v1/attestations/{id}）
  - 存证验证（POST /v1/attestations/{id}/verify）
  - 证据链追踪（GET /v1/traces/{delegation_id}）
  - 证据包导出（POST /v1/evidence-packages）
  - 锚点导出（POST /v1/anchors/export）

- **verifier.py**：存证验证
  - SHA-256 哈希重新计算对比
  - 未来时间检测（5 分钟容差）

- **trace_service.py**：证据链 DAG 追踪

#### 2.2.6 Web GUI（web_gui/）

- **app.py**（约 270 行）：FastAPI 应用
  - SSE 流式对话（/api/chat/stream）
  - 文件上传/下载/管理
  - 委托授权确认/取消接口
  - 系统重置接口
  - 账户充值接口

- **index.html**：单页应用
  - 三面板布局：对话 / 流程日志 / 服务目录
  - `marked.js` 实现 Markdown 流式渲染
  - `interactive_card` SSE 事件驱动确认卡片

---

## 三、ACT 四大域规范符合性

### 3.1 委托授权域（Delegation Domain）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| ISR（意图结构化记录） | ✅ 通过 | `intent_service.py` 创建 ISR，含 task_goal、金额上限、白名单、有效期 |
| IAC（意图授权凭证） | ✅ 通过 | `issuer.py` 签发 BOUNDED 模式 IAC，含完整约束条件 |
| Ed25519 签名 | ✅ 通过 | JCS 规范化后用独立 Ed25519 私钥签名，买方不持有私钥 |
| IAC 签名验证 | ✅ 通过 | PSP 从委托授权服务拉取公钥，验证 IAC 完整性 |
| 生命周期管理 | ✅ 通过 | 支持 Active/Suspended/Revoked/Expired 状态转换 |
| 绑定关系 | ✅ 通过 | UserAgentBinding → PaymentBinding 两级绑定链 |
| 存证 | ✅ 通过 | ISR 创建和 IAC 签发均异步提交 Ed25519 签名存证 |
| 公钥暴露 | ✅ 通过 | `GET /v1/public-key` 供 PSP 拉取签发公钥 |

### 3.2 商业交互域（Commerce Domain）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Agent Card 发现 | ✅ 通过 | `.well-known/agent-card.json` 标准端点 |
| 服务目录 | ✅ 通过 | `v1/catalog` 端点，含 service_id、价格、描述 |
| A2A Task/Message | ✅ 通过 | 创建 Task → 发送 Message → 获取 Artifact 完整协议 |
| HTTP 402 Payment-Needed | ✅ 通过 | 卖方返回 402 + Payment-Needed 头，携带订单信息 |
| 支付凭证验证 | ✅ 通过 | 卖方独立验证 Ed25519 签名 + amount 匹配 + seller_id 匹配 |
| Proof 防重用 | ✅ 通过 | proof_usage 表记录，禁止同一凭证重复使用 |
| 履约存证 | ✅ 通过 | 服务交付后异步提交 act:commerce:fulfillment-completed 存证 |

### 3.3 支付结算域（Payment Domain）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 19 步验证流水线 | ✅ 通过 | 完整的固定顺序支付处理流程 |
| 身份核验 | ✅ 通过 | 凭证归属验证 + 绑定验证 |
| IAC 策略执行 | ✅ 通过 | 卖方白名单、类别白名单、支付方法白名单 |
| 金额限额 | ✅ 通过 | 单笔限额 + 累计限额（iac_usage 表聚合） |
| 幂等保护 | ✅ 通过 | request_id + SHA-256 摘要防重放 |
| 时间戳验证 | ✅ 通过 | 5 分钟请求时间窗口 |
| Ed25519 签名支付凭证 | ✅ 通过 | PSP 签发 PaymentProof，含完整交易信息 + 签名 |
| 支付存证 | ✅ 通过 | trade 完成和 fulfillment 通知均提交存证 |

### 3.4 信任服务域（Trust Domain）

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 存证存储 | ✅ 通过 | 结构化 AttestationRecord 模型，含完整关联字段 |
| Ed25519 签名存证 | ✅ 通过 | PSP 和委托授权服务均对存证记录签名 |
| SHA-256 验证 | ✅ 通过 | 重新计算载荷哈希并比对 |
| 未来时间检测 | ✅ 通过 | 5 分钟容差窗口 |
| 证据链追踪 | ✅ 通过 | trace_service 按 delegation_id 追踪完整链路 |
| 上游链接 | ✅ 通过 | upstream_attestation_ids 构建 DAG 证据链 |
| 证据包导出 | ✅ 通过 | 按 delegation_id/trade_no 导出完整证据包 |

---

## 四、安全特性汇总

| 安全机制 | 实现位置 | 说明 |
|----------|----------|------|
| Ed25519 数字签名 | shared/signatures.py | JCS 规范化 + Ed25519，用于 IAC、PaymentProof、存证记录 |
| SHA-256 摘要 | shared/signatures.py | 载荷完整性校验 |
| 凭证归属验证 | demo_psp/identity_verifier.py | 验证凭证属于声明智能体 |
| 防重放 | demo_psp/payment_processor.py | request_id + SHA-256 幂等检查 |
| 时间戳窗口 | demo_psp/payment_processor.py | 5 分钟请求时效 |
| 双层绑定 | delegation_service/ | UserAgentBinding → PaymentBinding |
| IAC 约束执行 | demo_psp/policy_engine.py | 金额、卖方、类别、支付方法四重白名单 |
| Proof 防重用 | seller/payment_adapter.py | proof_usage 表唯一约束 |
| 金额独立验证 | seller/payment_adapter.py | 卖方独立校验 proof 中 amount 与 service price 匹配 |
| 存证签名链 | 各 attestation_outbox.py | 每个服务独立 Ed25519 签名存证 |

---

## 五、技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 全部 5 个微服务 |
| 数据库 | SQLite + aiosqlite | 每个服务独立 SQLite 数据库 |
| LLM | DeepSeek API (deepseek-v4-flash) | 买方对话推理、卖方 Skill 执行 |
| 密码学 | Ed25519 (cryptography库) | 数字签名、身份凭证 |
| 规范化 | RFC 8785 JCS | 签名前的 JSON 规范化 |
| 摘要 | SHA-256 | 载荷完整性、幂等检查摘要 |
| 文档处理 | python-docx | DOCX 文件翻译 |
| 前端 | 原生 HTML/JS + marked.js | SSE 流式对话界面 |
| 进程管理 | multiprocessing | 6 个进程并行启动 |
| 异步 | asyncio + httpx | 全链路异步 I/O |

---

## 六、书稿撰写适用性评估

### 6.1 优势

1. **完整的四域覆盖**：Demo 完整实现了 ACT 四层架构的全部环节，从委托授权到信任存证形成闭环，适合作为"ACT 协议实战"章节的核心案例。

2. **教学层次清晰**：
   - 每个域有独立的服务模块，边界明确
   - 19 步支付流水线可逐条对应 ACT 规范要求
   - 错误码体系覆盖全部异常场景（4 大类 36 个错误码）

3. **可视化效果好**：
   - Web GUI 三面板布局（对话/流程日志/服务目录）直观展示交易过程
   - 委托授权确认卡片演示"人工介入"机制
   - SSE 流式输出展示智能体"思考过程"
   - 流程日志面板实时展示 A2A 交互步骤

4. **密码学完整性**：
   - Ed25519 签名覆盖 IAC、PaymentProof、存证记录三层
   - SHA-256 摘要保障数据完整性
   - 防重放、防篡改、防重用机制完备

5. **架构清晰**：5 个独立微服务 + 共享模块的分层设计，便于在书稿中逐个讲解

### 6.2 书稿使用建议

1. **按域分节讲解**：
   - 第 1 节：委托授权域 — ISR → IAC 签发流程，Ed25519 签名机制
   - 第 2 节：商业交互域 — A2A 协议、Agent Card 发现、HTTP 402 支付协商
   - 第 3 节：支付结算域 — 19 步验证流水线，策略引擎
   - 第 4 节：信任服务域 — 存证记录、证据链追踪

2. **重点代码片段**：
   - `issuer.py` 的 `issue()` 方法：IAC 签发逻辑
   - `payment_processor.py` 的 `process_payment()`：支付流水线
   - `iac_verifier.py` 的 `verify_iac()`：签名验证
   - `commerce_controller.py` 的 `handle_service_invocation()`：402 支付拦截模式
   - `signatures.py` 的 `sign_json()/verify_json()`：密码学基础

3. **适合配图的环节**：
   - 系统架构拓扑图
   - ACT 四域数据流图
   - 委托授权确认卡片截图
   - 支付流水线步骤图
   - 证据链 DAG 示意图

### 6.3 边界声明（需在书稿中注明）

- 本项目为**教学性实现**，身份标识、凭证、支付方法、存证均为本地模拟
- 不实现 ACT Trust Chain（链上锚定）
- 不使用 GB/Z 185.2 正式身份码
- 不处理真实资金
- 未经过 ACT、GB/Z 185、APOP 一致性认证

---

## 七、文件统计

| 模块 | 文件数 | 核心代码量（估算） |
|------|--------|---------------------|
| shared/ | 13 | ~800 行 |
| buyer/ | 9 | ~1,500 行 |
| delegation_service/ | 9 | ~1,200 行 |
| seller/ | 15 | ~2,000 行 |
| demo_psp/ | 12 | ~1,800 行 |
| trust_service/ | 8 | ~800 行 |
| web_gui/ | 3 | ~1,500 行 (含 HTML) |
| llm/ | 4 | ~300 行 |
| **总计** | **~73** | **~9,900 行** |

---

## 八、关键 API 端点汇总

| 服务 | 方法 | 端点 | 说明 |
|------|------|------|------|
| delegation | POST | /v1/intents | 创建 ISR |
| delegation | POST | /v1/delegations | 签发 IAC |
| delegation | GET | /v1/public-key | 暴露签发公钥 |
| delegation | GET | /v1/delegations/{id}/status | IAC 状态查询 |
| seller | GET | /.well-known/agent-card.json | Agent Card 发现 |
| seller | GET | /v1/catalog | 服务目录 |
| seller | POST | /v1/a2a/tasks | 创建 A2A Task |
| seller | POST | /v1/a2a/tasks/{id}/messages | 发送 A2A Message |
| seller | POST | /v1/a2a/tasks/{id}/pay | 支付后履约回调 |
| seller | POST | /v1/services/{id}/invoke | 服务调用（可返回 402） |
| demo_psp | POST | /v1/payments | 支付处理 |
| demo_psp | POST | /v1/payment-proofs/verify | 支付凭证验证 |
| demo_psp | GET | /v1/subaccounts/{id} | 账户余额查询 |
| demo_psp | POST | /v1/subaccounts/{id}/topup | 账户充值 |
| trust | POST | /v1/attestations | 提交存证 |
| trust | POST | /v1/attestations/{id}/verify | 验证存证 |
| trust | GET | /v1/traces/{delegation_id} | 证据链追踪 |
| trust | POST | /v1/evidence-packages | 证据包导出 |
| web_gui | GET | /api/chat/stream | SSE 流式对话 |
| web_gui | POST | /api/delegation/confirm | 委托确认 |
| web_gui | POST | /api/delegation/cancel | 委托取消 |
| web_gui | POST | /api/reset | 系统重置 |

---

## 九、结论

本 Demo 是一个**教学级别的高质量 ACT 协议参考实现**，完整覆盖 ACT 四域架构的各个环节。代码结构清晰、模块边界明确、密码学基础扎实（Ed25519 签名 + SHA-256 摘要 + JCS 规范化），19 步支付验证流水线完整演示了 ACT 支付域的合规检查逻辑。配备 Web GUI 可视化界面和 SSE 流式对话，适合作为书稿中"智能体可信交易"章节的核心实践案例。

**ACT 合规评分：通过**（四大域全部达标，教学级别）
