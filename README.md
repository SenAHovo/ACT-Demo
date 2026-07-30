# ACT智能体自主委托支付Demo

## 项目简介

本 Demo 是《智能互联》书稿中"智能体交易"章节的配套实践案例，以 ACT（Agentic Commerce Trust Protocol，由支付宝提出）"智能体自主委托支付"场景为业务主线，参考 GB/Z 185 系列指导性技术文件组织智能体身份、描述、发现和交互能力，并在支付提供方适配层中预留 APOP 未来接入边界。

## 核心流程

> 委托人提出任务与预算边界 → 买方智能体形成结构化意图 → 委托授权服务签发BOUNDED模式IAC → 买方智能体发现卖方智能体及其服务 → 买方智能体自主选择三项付费服务 → 卖方智能体返回HTTP 402支付要求 → 买方智能体向支付服务方发起支付 → 支付服务方核验授权并模拟扣款 → 买方智能体携带支付凭证再次请求服务 → 卖方智能体验证凭证并交付结果 → 各域异步生成存证记录 → 信任服务提供方形成可查询、可验证的证据链 → 买方智能体向委托人返回报告和任务账单

## 技术栈

- **语言**: Python 3.10+
- **Web框架**: FastAPI
- **数据库**: SQLite
- **LLM**: DeepSeek API (deepseek-v4-flash)
- **签名算法**: Ed25519
- **摘要算法**: SHA-256 + RFC 8785 JCS规范化

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
#    将 .env.example 复制为 .env，然后编辑填入你的 DEEPSEEK_API_KEY
#    Linux/macOS: cp .env.example .env
#    Windows:     copy .env.example .env

# 3. 启动 Demo
python run_demo.py
```

## 项目结构

```text
act-autonomous-payment-demo/
├── buyer/                    # 买方智能体
├── delegation_service/       # 委托授权、身份与绑定服务
├── seller/                   # 卖方智能体及三项Skill
├── demo_psp/                 # 支付服务方
├── trust_service/            # 信任服务提供方
├── shared/                   # 共享数据结构与工具
├── llm/                      # DeepSeek API适配层
├── tests/                    # 测试用例
└── logs/                     # 运行日志
```

## 案例边界声明

本案例中的项目自定义身份标识、本地凭证、本地余额支付方法、服务目录接口、交互接口和链下存证服务均为教学性实现，不由ACT、国家标准发布机构或中国银联提供。案例不处理真实资金，不实现ACT Trust Chain，不使用GB/Z 185.2正式身份码，不宣称APOP报文兼容，也未经过ACT、GB/Z 185、APOP、A2A或Agent Skills相关一致性认证，不能直接用于生产环境。
