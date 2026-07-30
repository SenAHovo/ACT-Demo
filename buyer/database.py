"""
买方智能体数据库模块
"""

import os, aiosqlite

DB_PATH = os.getenv("BUYER_DB_PATH", "./data/buyer.db")

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
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            service_id TEXT NOT NULL,
            trade_no TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            payload TEXT NOT NULL,
            source_artifact_ids TEXT NOT NULL DEFAULT '[]',
            retrieved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            intent_id TEXT,
            delegation_id TEXT,
            service_id TEXT NOT NULL,
            trade_no TEXT,
            amount TEXT,
            currency TEXT DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS attestation_outbox (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            submission_status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0
        );
        """)
        await db.commit()
    finally:
        await db.close()
