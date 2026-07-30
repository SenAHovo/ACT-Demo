"""
delegation_service/ — 委托授权、身份与绑定服务

运行端口: 8000
"""

from .app import app, run_demo_init
from .database import init_db

__all__ = ["app", "run_demo_init", "init_db"]
