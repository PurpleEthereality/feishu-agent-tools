"""飞书 Agent 工具插件单元测试。"""

from __future__ import annotations

import asyncio
import types
from typing import Any

from core.plugin import FeishuAgentToolsPlugin


class _DummyLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass

    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass


def _make_plugin() -> FeishuAgentToolsPlugin:
    plugin = FeishuAgentToolsPlugin()
    plugin._set_context(types.SimpleNamespace(logger=_DummyLogger()))
    plugin.set_plugin_config(
        {
            "plugin": {"enabled": True, "config_version": "1.0.0"},
            "credentials": {"app_id": "cli_x", "app_secret": "s", "region": "feishu"},
        }
    )
    return plugin


def test_platform_guard() -> None:
    """平台守卫：飞书放行，其它平台拦截。"""

    plugin = _make_plugin()
    assert plugin._guard({"platform": "feishu"}) is None
    assert plugin._guard({}) is None
    assert "仅飞书" in (plugin._guard({"platform": "qq"}) or "")


def test_tool_blocked_outside_feishu() -> None:
    """非飞书聊天调用工具应被拦截且不执行飞书 API。"""

    plugin = _make_plugin()
    result = asyncio.run(plugin.tool_send_message(receive_id="ou_x", receive_id_type="open_id", text="hi", platform="qq"))
    assert "仅飞书" in str(result)


def test_tool_missing_param() -> None:
    """飞书聊天但缺参数应报参数错误。"""

    plugin = _make_plugin()
    result = asyncio.run(plugin.tool_send_message(platform="feishu"))
    assert "缺少" in str(result)


def test_tool_success() -> None:
    """飞书聊天正常调用返回结果。"""

    plugin = _make_plugin()

    async def fake_send(settings, receive_id, receive_id_type, text):
        return "om_test"

    plugin.message_send_text = fake_send
    result = asyncio.run(
        plugin.tool_send_message(receive_id="ou_x", receive_id_type="open_id", text="hi", platform="feishu")
    )
    assert result["data"]["sent"] is True
    assert result["data"]["message_id"] == "om_test"
