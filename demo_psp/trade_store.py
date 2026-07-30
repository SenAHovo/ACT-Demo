"""
共享交易存储模块

整个 PSP 进程内唯一的交易记录和凭证存储。
payment_processor.py 写入，proof_service.py 读取。
"""
from __future__ import annotations

# 支付凭证存储: trade_no → proof_data
_proofs: dict[str, dict] = {}

# 交易记录存储: trade_no → payment_record
_trades: dict[str, dict] = {}


def save_proof(trade_no: str, proof_data: dict) -> None:
    """保存支付凭证到共享存储。"""
    _proofs[trade_no] = proof_data


def get_proof(trade_no: str) -> dict | None:
    """从共享存储获取支付凭证。"""
    return _proofs.get(trade_no)


def save_trade(trade_no: str, trade_record: dict) -> None:
    """保存交易记录到共享存储。"""
    _trades[trade_no] = trade_record


def get_trade(trade_no: str) -> dict | None:
    """从共享存储获取交易记录。"""
    return _trades.get(trade_no)


def reset_store() -> None:
    """重置所有存储（用于 Demo 重置）。"""
    _proofs.clear()
    _trades.clear()
