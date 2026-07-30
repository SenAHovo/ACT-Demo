"""
委托授权服务数据库模块

SQLite 数据库定义、表创建和连接管理。
使用 aiosqlite 实现异步数据库操作。
"""

from __future__ import annotations

import os

import aiosqlite

from shared.time_utils import utc_now, to_iso

# 数据库路径，可通过环境变量覆盖
DB_PATH = os.getenv("DELEGATION_DB_PATH", "./data/delegation_service.db")


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（调用方负责关闭）。"""
    # 确保父目录存在
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """初始化数据库表结构。"""
    db = await get_db()
    try:
        await db.executescript("""
        -- 智能体身份
        CREATE TABLE IF NOT EXISTS agent_identities (
            agent_id TEXT PRIMARY KEY,
            agent_id_scheme TEXT NOT NULL DEFAULT 'demo',
            credential_id TEXT NOT NULL,
            public_key TEXT NOT NULL,
            credential_status TEXT NOT NULL DEFAULT 'ACTIVE',
            service_endpoint TEXT,
            issued_at TEXT NOT NULL,
            expires_at TEXT
        );

        -- 凭证历史
        CREATE TABLE IF NOT EXISTS credential_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credential_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            reason TEXT
        );

        -- 委托人-买方智能体绑定
        CREATE TABLE IF NOT EXISTS user_agent_bindings (
            user_agent_binding_id TEXT PRIMARY KEY,
            delegator_id TEXT NOT NULL,
            buyer_agent_id TEXT NOT NULL,
            authorization_scope TEXT NOT NULL DEFAULT 'BOUNDED',
            authentication_method TEXT NOT NULL DEFAULT 'demo_local_credential',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            expires_at TEXT
        );

        -- 支付绑定
        CREATE TABLE IF NOT EXISTS payment_bindings (
            payment_binding_id TEXT PRIMARY KEY,
            user_agent_binding_id TEXT NOT NULL,
            buyer_agent_id TEXT NOT NULL,
            payment_method_id TEXT NOT NULL,
            sub_account_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            valid_from TEXT NOT NULL,
            valid_until TEXT
        );

        -- 身份认证断言
        CREATE TABLE IF NOT EXISTS authentication_assertions (
            assertion_id TEXT PRIMARY KEY,
            subject_agent_id TEXT NOT NULL,
            verifier_agent_id TEXT NOT NULL,
            credential_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            authenticated_at TEXT NOT NULL,
            expires_at TEXT,
            signature TEXT NOT NULL
        );

        -- 意图结构化记录
        CREATE TABLE IF NOT EXISTS intents (
            intent_id TEXT PRIMARY KEY,
            task_goal TEXT NOT NULL,
            delegation_mode TEXT NOT NULL DEFAULT 'BOUNDED',
            validity_start_time TEXT NOT NULL,
            validity_end_time TEXT NOT NULL,
            max_total_amount TEXT NOT NULL,
            max_single_amount TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            allowed_sellers TEXT NOT NULL DEFAULT '[]',
            allowed_categories TEXT NOT NULL DEFAULT '[]',
            allowed_payment_methods TEXT NOT NULL DEFAULT '[]',
            agent_id TEXT NOT NULL,
            agent_id_scheme TEXT NOT NULL DEFAULT 'demo',
            user_agent_binding_id TEXT NOT NULL,
            confirmation_timestamp TEXT NOT NULL
        );

        -- 意图授权凭证
        CREATE TABLE IF NOT EXISTS delegations (
            delegation_id TEXT PRIMARY KEY,
            intent_id TEXT NOT NULL,
            delegator_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_id_scheme TEXT NOT NULL DEFAULT 'demo',
            user_agent_binding_id TEXT NOT NULL,
            delegation_mode TEXT NOT NULL DEFAULT 'BOUNDED',
            validity_start_time TEXT NOT NULL,
            validity_end_time TEXT NOT NULL,
            max_total_amount TEXT NOT NULL,
            max_single_amount TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            allowed_sellers TEXT NOT NULL DEFAULT '[]',
            allowed_categories TEXT NOT NULL DEFAULT '[]',
            allowed_payment_methods TEXT NOT NULL DEFAULT '[]',
            source_isr_digest TEXT NOT NULL,
            status_reference TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Active',
            proof TEXT NOT NULL
        );

        -- 授权状态变更历史
        CREATE TABLE IF NOT EXISTS delegation_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delegation_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            reason TEXT
        );
        """)
        await db.commit()

        # 兼容旧数据库：添加 status_reference 列（IAC 签名验证需要）
        try:
            await db.execute(
                "ALTER TABLE delegations ADD COLUMN status_reference TEXT NOT NULL DEFAULT ''"
            )
            await db.commit()
        except Exception:
            pass  # 列已存在则忽略
    finally:
        await db.close()
