"""
DemoPSP 数据库模块

SQLite 数据库定义和连接管理。
"""

from __future__ import annotations

import os

import aiosqlite

DB_PATH = os.getenv("PSP_DB_PATH", "./data/demo_psp.db")


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
        -- 模拟子账户
        CREATE TABLE IF NOT EXISTS sub_accounts (
            sub_account_id TEXT PRIMARY KEY,
            buyer_agent_id TEXT NOT NULL,
            agent_id_scheme TEXT NOT NULL DEFAULT 'demo',
            payment_binding_id TEXT NOT NULL,
            balance TEXT NOT NULL DEFAULT '5.00',
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        -- 支付记录
        CREATE TABLE IF NOT EXISTS payments (
            trade_no TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            out_trade_no TEXT NOT NULL,
            delegation_id TEXT NOT NULL,
            user_agent_binding_id TEXT NOT NULL,
            payment_binding_id TEXT NOT NULL,
            sub_account_id TEXT NOT NULL,
            buyer_agent_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            service_category TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            resource_digest TEXT NOT NULL,
            session_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            amount TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            method_id TEXT NOT NULL,
            trade_status TEXT NOT NULL DEFAULT 'CREATE',
            created_at TEXT NOT NULL,
            paid_at TEXT,
            fulfilled_at TEXT
        );

        -- IAC 累计使用额度追踪
        CREATE TABLE IF NOT EXISTS iac_usage (
            delegation_id TEXT PRIMARY KEY,
            total_spent TEXT NOT NULL DEFAULT '0.00',
            currency TEXT NOT NULL DEFAULT 'CNY',
            last_updated TEXT NOT NULL
        );

        -- 幂等请求记录
        CREATE TABLE IF NOT EXISTS used_requests (
            request_id TEXT PRIMARY KEY,
            request_digest TEXT NOT NULL,
            trade_no TEXT,
            recorded_at TEXT NOT NULL
        );

        -- 支付凭证
        CREATE TABLE IF NOT EXISTS payment_proofs (
            trade_no TEXT PRIMARY KEY,
            proof_data TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'SUCCESS'
        );

        -- 交易状态变更历史
        CREATE TABLE IF NOT EXISTS trade_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_no TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL
        );

        -- 存证出箱
        CREATE TABLE IF NOT EXISTS attestation_outbox (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            local_record_path TEXT,
            payload_hash TEXT NOT NULL,
            payload_json TEXT DEFAULT '',
            signature TEXT,
            submission_status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0
        );
        """)
        await db.commit()

        # 兼容旧数据库：添加 payload_json 列
        try:
            await db.execute(
                "ALTER TABLE attestation_outbox ADD COLUMN payload_json TEXT DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # 列已存在则忽略
    finally:
        await db.close()
