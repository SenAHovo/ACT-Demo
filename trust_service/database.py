"""
信任服务数据库模块
"""

import os, aiosqlite

DB_PATH = os.getenv("TRUST_DB_PATH", "./data/trust_service.db")

async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=DELETE")
    await ensure_tables(db)
    return db


async def ensure_tables(db: aiosqlite.Connection):
    """确保数据库表存在（每次连接都执行，幂等安全）。"""
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS attestation_records (
        attestation_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        event_time TEXT NOT NULL,
        record_created_at TEXT NOT NULL,
        intent_id TEXT,
        delegation_id TEXT,
        session_id TEXT,
        task_id TEXT,
        out_trade_no TEXT,
        trade_no TEXT,
        upstream_links TEXT NOT NULL DEFAULT '[]',
        participants TEXT NOT NULL DEFAULT '[]',
        payload_hash TEXT NOT NULL,
        hash_algorithm TEXT NOT NULL DEFAULT 'SHA-256',
        event_body TEXT,
        signer_id TEXT NOT NULL,
        signature TEXT,
        source_record_ref TEXT
    );
    CREATE TABLE IF NOT EXISTS verification_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attestation_id TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        result TEXT NOT NULL,
        reason TEXT
    );
    """)
    await db.commit()

async def init_db() -> None:
    db = await get_db()
    try:
        await ensure_tables(db)
        # 额外表（不常用，仅在 init_db 创建）
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS submission_retries (
            attestation_id TEXT PRIMARY KEY,
            last_try_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS evidence_packages (
            package_id TEXT PRIMARY KEY,
            query_params TEXT NOT NULL,
            attestation_ids TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        await db.commit()
    finally:
        await db.close()
