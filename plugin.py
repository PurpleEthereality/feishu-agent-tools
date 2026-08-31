"""飞书 Agent 工具插件入口。"""

from __future__ import annotations

from .core import FeishuAgentToolsPlugin


def create_plugin() -> FeishuAgentToolsPlugin:
    """创建飞书 Agent 工具插件实例。"""

    return FeishuAgentToolsPlugin()
