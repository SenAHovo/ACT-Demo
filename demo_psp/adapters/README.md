# demo_psp/adapters/ — 支付适配器实现

## 职责

通过PaymentProviderAdapter统一接口隔离具体的支付实现方式。

## 当前实现

**LocalBalanceAdapter** (`local_balance.py`)：本地模拟余额支付，操作内存/SQLite中的模拟子账户。

## 未来扩展点

**APOPAdapter**：在获得APOP受邀接入资料后，按统一接口实现真实支付通道接入。当前不使用APOP报文名、接口名或声称APOP兼容。

## 接口约定

```python
class PaymentProviderAdapter:
    async def authorize(self, request): ...
    async def query(self, out_trade_no): ...
    async def verify_proof(self, proof): ...
    async def notify_fulfillment(self, trade_no): ...
```
