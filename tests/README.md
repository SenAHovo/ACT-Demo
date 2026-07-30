# tests/ — 测试用例

## 当前测试覆盖

当前自动化测试 (`test_shared.py`) 覆盖 `shared/` 基础模块：

| 测试函数 | 覆盖模块 |
|---|---|
| `test_money` | 金额解析、币种校验、限额断言 |
| `test_time` | UTC 时间工具 |
| `test_encoding` | Base64URL 编解码 |
| `test_canonicalization` | 确定性 JSON 序列化（键排序） |
| `test_signatures` | Ed25519 签名生成/验证、SHA-256 摘要 |
| `test_identity` | Agent ID 格式校验与生成 |
| `test_schemas` | IAC 等核心数据模型构造 |
| `test_errors` | 错误码与异常 |

## 运行方式

```bash
# 运行全部测试（当前 8 个）
pytest tests/

# 运行带覆盖率报告
pytest tests/ --cov=. --cov-report=html
```

## 说明

当前测试主要覆盖 `shared/` 共享工具模块。端到端交易流程测试、安全测试和协议兼容性测试尚未形成可重复执行的自动化测试套件，计划在后续版本中补充。
