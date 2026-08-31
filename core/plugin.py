"""飞书 Agent 工具插件：把飞书各功能注册为 AI 工具。"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional, cast

from maibot_sdk import MaiBotPlugin, PluginConfigBase, Tool

from .client import FeishuAgentClientMixin
from .constants import TARGET_PLATFORM
from .settings import FeishuAgentToolsSettings


def _tool_result(**fields: Any) -> Dict[str, Any]:
    """构造统一工具返回。"""

    return {"data": fields}


class FeishuAgentToolsPlugin(FeishuAgentClientMixin, MaiBotPlugin):
    """把飞书知识库/日历/文档/消息/审批/多维表格注册为 AI 工具。"""

    config_model: ClassVar[type[PluginConfigBase] | None] = FeishuAgentToolsSettings

    async def on_load(self) -> None:
        """插件加载日志。"""

        settings = self._load_settings()
        if settings.should_connect():
            self.ctx.logger.info("飞书 Agent 工具插件已加载")
        else:
            self.ctx.logger.info("飞书 Agent 工具插件保持空闲状态，因为插件未启用")

    async def on_unload(self) -> None:
        """插件卸载清理。"""

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """配置热更新。"""

        del scope, config_data, version

    def _load_settings(self) -> FeishuAgentToolsSettings:
        """返回当前强类型配置。"""

        return cast(FeishuAgentToolsSettings, self.config)

    def _guard(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """运行期守卫：非飞书聊天返回错误提示。"""

        platform = str(kwargs.get("platform") or "").strip()
        if platform and platform != TARGET_PLATFORM:
            return f"该工具仅飞书聊天可用，当前平台为 {platform}"
        return None

    def _fail(self, error: str) -> Dict[str, Any]:
        """返回错误结果。"""

        return {"error": error}

    # ---- 知识库 / 文档 ----

    @Tool(
        "feishu_search_wiki",
        description="在飞书知识库中按关键词搜索文档节点，返回匹配的文档标题与节点信息。",
        parameters={"query": {"type": "string", "description": "搜索关键词"}, "limit": {"type": "integer", "description": "返回数量上限，默认5"}},
    )
    async def tool_search_wiki(self, query: str = "", limit: int = 5, **kwargs: Any) -> Dict[str, Any]:
        """搜索飞书知识库。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not query:
            return self._fail("缺少搜索关键词 query")
        settings = self._load_settings()
        try:
            items = await self.wiki_search_nodes(settings, query, count=int(limit or 5))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(items=[self._serializable(item) for item in items])

    @Tool(
        "feishu_list_wiki",
        description="列出飞书知识库空间及其下的节点，用于浏览知识库结构。",
        parameters={"space_id": {"type": "string", "description": "知识库空间 ID（留空则列出全部空间）"}, "parent_node_token": {"type": "string", "description": "父节点 token，用于下钻（可选）"}},
    )
    async def tool_list_wiki(self, space_id: str = "", parent_node_token: str = "", **kwargs: Any) -> Dict[str, Any]:
        """列出飞书知识库空间或节点。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        settings = self._load_settings()
        try:
            if space_id:
                items = await self.wiki_list_nodes(settings, space_id, parent_node_token)
            else:
                items = await self.wiki_list_spaces(settings)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(items=[self._serializable(item) for item in items])

    @Tool(
        "feishu_read_document",
        description="读取飞书文档（docx）的纯文本正文，按 document_id。",
        parameters={"document_id": {"type": "string", "description": "飞书文档 ID（取自知识库节点或文档链接）"}},
    )
    async def tool_read_document(self, document_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        """读取飞书文档正文。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not document_id:
            return self._fail("缺少 document_id")
        settings = self._load_settings()
        try:
            content = await self.docx_get_raw_content(settings, document_id)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        if not content:
            return self._fail("文档内容为空或无法读取")
        return _tool_result(document_id=document_id, content=content[:8000])

    # ---- 消息收发 ----

    @Tool(
        "feishu_send_message",
        description="向指定飞书用户（open_id）或群（chat_id）主动发送文本消息。",
        parameters={
            "receive_id": {"type": "string", "description": "接收者 ID（open_id 或 chat_id）"},
            "receive_id_type": {"type": "string", "description": "ID 类型：open_id 或 chat_id"},
            "text": {"type": "string", "description": "要发送的文本内容"},
        },
    )
    async def tool_send_message(
        self,
        receive_id: str = "",
        receive_id_type: str = "",
        text: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送飞书消息。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not receive_id or not receive_id_type or not text:
            return self._fail("缺少 receive_id / receive_id_type / text")
        if receive_id_type not in {"open_id", "chat_id"}:
            return self._fail("receive_id_type 只能是 open_id 或 chat_id")
        settings = self._load_settings()
        try:
            message_id = await self.message_send_text(settings, receive_id, receive_id_type, text)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(sent=True, message_id=message_id)

    @Tool(
        "feishu_reply_message",
        description="回复某条飞书消息。",
        parameters={"message_id": {"type": "string", "description": "要回复的消息 ID"}, "text": {"type": "string", "description": "回复内容"}},
    )
    async def tool_reply_message(self, message_id: str = "", text: str = "", **kwargs: Any) -> Dict[str, Any]:
        """回复飞书消息。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not message_id or not text:
            return self._fail("缺少 message_id 或 text")
        settings = self._load_settings()
        try:
            new_message_id = await self.message_reply_text(settings, message_id, text)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(sent=True, message_id=new_message_id)

    @Tool(
        "feishu_recall_message",
        description="撤回一条飞书消息。",
        parameters={"message_id": {"type": "string", "description": "要撤回的消息 ID"}},
    )
    async def tool_recall_message(self, message_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        """撤回飞书消息。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not message_id:
            return self._fail("缺少 message_id")
        settings = self._load_settings()
        try:
            await self.message_recall(settings, message_id)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(recalled=True)

    # ---- 日历 ----

    @Tool(
        "feishu_list_calendar_events",
        description="按时间范围列出飞书日历日程。",
        parameters={
            "calendar_id": {"type": "string", "description": "日历 ID"},
            "start_time": {"type": "string", "description": "开始时间（毫秒时间戳）"},
            "end_time": {"type": "string", "description": "结束时间（毫秒时间戳）"},
        },
    )
    async def tool_list_calendar_events(
        self,
        calendar_id: str = "",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """列出飞书日程。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not calendar_id or not start_time or not end_time:
            return self._fail("缺少 calendar_id / start_time / end_time")
        settings = self._load_settings()
        try:
            items = await self.calendar_list_events(settings, calendar_id, start_time, end_time)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(items=[self._serializable(item) for item in items])

    # ---- 审批 ----

    @Tool(
        "feishu_list_approvals",
        description="按时间范围列出飞书审批实例。",
        parameters={
            "approval_code": {"type": "string", "description": "审批定义 code"},
            "start_time": {"type": "integer", "description": "开始时间（秒时间戳）"},
            "end_time": {"type": "integer", "description": "结束时间（秒时间戳）"},
        },
    )
    async def tool_list_approvals(
        self,
        approval_code: str = "",
        start_time: int = 0,
        end_time: int = 0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """列出飞书审批实例。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not approval_code:
            return self._fail("缺少 approval_code")
        settings = self._load_settings()
        try:
            items = await self.approval_list_instances(settings, approval_code, start_time, end_time)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(items=[self._serializable(item) for item in items])

    # ---- 多维表格 ----

    @Tool(
        "feishu_list_table_records",
        description="列出飞书多维表格数据表的记录。",
        parameters={
            "app_token": {"type": "string", "description": "多维表格 app_token"},
            "table_id": {"type": "string", "description": "数据表 ID"},
            "page_size": {"type": "integer", "description": "返回条数上限，默认50"},
        },
    )
    async def tool_list_table_records(
        self,
        app_token: str = "",
        table_id: str = "",
        page_size: int = 50,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """列出多维表格记录。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not app_token or not table_id:
            return self._fail("缺少 app_token 或 table_id")
        settings = self._load_settings()
        try:
            items = await self.bitable_list_records(settings, app_token, table_id, page_size=int(page_size or 50))
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(items=[self._serializable(item) for item in items])

    @Tool(
        "feishu_create_table_record",
        description="在飞书多维表格数据表新增一条记录。",
        parameters={
            "app_token": {"type": "string", "description": "多维表格 app_token"},
            "table_id": {"type": "string", "description": "数据表 ID"},
            "fields": {"type": "object", "description": "字段名到字段值的映射，如 {\"姓名\":\"张三\"}"},
        },
    )
    async def tool_create_table_record(
        self,
        app_token: str = "",
        table_id: str = "",
        fields: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """新增多维表格记录。"""

        if error := self._guard(kwargs):
            return self._fail(error)
        if not app_token or not table_id or not fields:
            return self._fail("缺少 app_token / table_id / fields")
        settings = self._load_settings()
        try:
            record = await self.bitable_create_record(settings, app_token, table_id, fields)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"{type(exc).__name__}: {exc}")
        return _tool_result(created=record)
