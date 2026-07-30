"""
web_gui/ — Web GUI 服务

提供对话面板、服务卡片、文件管理功能。
运行端口: 8080
"""

from .app import app, create_agent

__all__ = ["app", "create_agent"]
