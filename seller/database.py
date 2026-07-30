"""
卖方智能体数据库模块
"""

from __future__ import annotations

import os
import aiosqlite

DB_PATH = os.getenv("SELLER_DB_PATH", "./data/seller.db")


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS service_catalog (
            service_id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            price TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            availability TEXT NOT NULL DEFAULT 'ACTIVE',
            price_valid_until TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            buyer_agent_id TEXT NOT NULL,
            assertion_id TEXT,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE IF NOT EXISTS service_tasks (
            task_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'SUBMITTED',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_messages (
            message_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            received_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_invocations (
            invoke_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            input_digest TEXT NOT NULL,
            delegation_id TEXT,
            buyer_agent_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS seller_orders (
            out_trade_no TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            resource_digest TEXT NOT NULL,
            amount TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            trade_no TEXT,
            status TEXT NOT NULL DEFAULT 'WAIT_BUYER_PAY',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            session_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            trade_no TEXT,
            content_digest TEXT NOT NULL,
            payload TEXT NOT NULL,
            source_artifact_ids TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proof_usage (
            trade_no TEXT PRIMARY KEY,
            usage_count INTEGER NOT NULL DEFAULT 0,
            first_used_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attestation_outbox (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT DEFAULT '',
            submission_status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS a2a_tasks (
            task_id TEXT PRIMARY KEY,
            buyer_agent_id TEXT NOT NULL,
            delegation_id TEXT DEFAULT '',
            goal TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'CREATED',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS a2a_messages (
            message_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES a2a_tasks(task_id)
        );
        """)
        await db.commit()
    finally:
        await db.close()
