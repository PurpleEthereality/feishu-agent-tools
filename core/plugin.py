"""飞书 Agent 工具插件：把飞书各功能注册为 AI 工具。"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional, cast

from maibot_sdk import MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .client import FeishuAgentClientMixin
from .constants import TARGET_PLATFORM
from .settings import FeishuAgentToolsSettings


def _ok(content: str, **data: Any) -> Dict[str, Any]:
    """构造成功结果：给 LLM 阅读的文字放 content，原始数据放 data。"""

    return {"content": content, "data": data}


def _err(content: str) -> Dict[str, Any]:
    """构造失败结果：返回可读错误，避免异常堆栈泄漏。"""

    return {"content": content, "error": content}


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

        self.ctx.logger.info("飞书 Agent 工具插件已卸载")

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        """配置热更新。"""

        del config_data
        self.ctx.logger.debug("飞书 Agent 工具插件配置已更新: scope=%s version=%s", scope, version)

    def _load_settings(self) -> FeishuAgentToolsSettings:
        """返回当前强类型配置。"""

        return cast(FeishuAgentToolsSettings, self.config)

    def _guard(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """运行期守卫：只在飞书聊天中放行。

        拿不到平台上下文时按「非飞书」处理（fail-closed）：否则任何丢失
        平台信息的调用都能绕过守卫直接打到飞书 API。
        """

        platform = str(kwargs.get("platform") or "").strip()
        if platform != TARGET_PLATFORM:
            return f"该工具仅飞书聊天可用，当前平台为 {platform or '未知'}"
        return None

    # ---- 知识库 / 文档 ----

    @Tool(
        "feishu_search_wiki",
        brief_description="在飞书知识库中按关键词搜索文档",
        detailed_description=(
            "当用户询问的资料可能在飞书知识库里时使用。返回匹配文档的标题与节点信息；"
            "拿到 node_token/obj_token 后可再用 feishu_read_document 读取正文。"
        ),
        parameters=[
            ToolParameterInfo(name="query", param_type=ToolParamType.STRING, description="搜索关键词", required=True),
            ToolParameterInfo(
                name="limit",
                param_type=ToolParamType.INTEGER,
                description="返回数量上限",
                required=False,
                default=5,
            ),
        ],
    )
    async def tool_search_wiki(self, query: str = "", limit: int = 5, **kwargs: Any) -> Dict[str, Any]:
        """搜索飞书知识库。"""

        if error := self._guard(kwargs):
            return _err(error)
        if not query:
            return _err("缺少搜索关键词 query")
        settings = self._load_settings()
        try:
            items = await self.wiki_search_nodes(settings, query, count=max(1, min(int(limit or 5), 20)))
        except Exception as exc:  # noqa: BLE001
            return _err(f"搜索飞书知识库失败：{type(exc).__name__}: {exc}")
        if not items:
            return _ok(f"飞书知识库中没有找到与「{query}」匹配的文档。", items=[])
        lines = [f"飞书知识库搜索「{query}」命中 {len(items)} 条："]
        for index, item in enumerate(items, start=1):
            node = self._serializable(item)
            title = str(node.get("title") or node.get("node_token") or "未命名")
            lines.append(f"{index}. {title}（node_token={node.get('node_token') or node.get('obj_token') or ''}）")
        return _ok("\n".join(lines), items=[self._serializable(item) for item in items])

    @Tool(
        "feishu_list_wiki",
        brief_description="浏览飞书知识库的空间与节点结构",
        detailed_description=(
            "不传 space_id 时列出全部知识库空间；传 space_id 时列出该空间下的节点，"
            "可用 parent_node_token 向下钻取。用于在不知道文档 ID 时先摸清知识库结构。"
        ),
        parameters=[
            ToolParameterInfo(
                name="space_id",
                param_type=ToolParamType.STRING,
                description="知识库空间 ID（留空则列出全部空间）",
                required=False,
            ),
            ToolParameterInfo(
                name="parent_node_token",
                param_type=ToolParamType.STRING,
                description="父节点 token，用于下钻（可选）",
                required=False,
            ),
        ],
    )
    async def tool_list_wiki(self, space_id: str = "", parent_node_token: str = "", **kwargs: Any) -> Dict[str, Any]:
        """列出飞书知识库空间或节点。"""

        if error := self._guard(kwargs):
            return _err(error)
        settings = self._load_settings()
        try:
            if space_id:
                items = await self.wiki_list_nodes(settings, space_id, parent_node_token)
                scope = f"空间 {space_id} 的节点"
            else:
                items = await self.wiki_list_spaces(settings)
                scope = "知识库空间"
        except Exception as exc:  # noqa: BLE001
            return _err(f"浏览飞书知识库失败：{type(exc).__name__}: {exc}")
        if not items:
            return _ok(f"飞书知识库没有返回任何{scope}。", items=[])
        serialized = [self._serializable(item) for item in items]
        return _ok(f"共返回 {len(serialized)} 个{scope}。", items=serialized)

    @Tool(
        "feishu_read_document",
        brief_description="读取飞书文档（docx）的纯文本正文",
        detailed_description=(
            "按 document_id 读取飞书文档正文，返回内容会被截断到 8000 字以内。"
            "document_id 可从 feishu_search_wiki / feishu_list_wiki 的结果中获得。"
        ),
        parameters=[
            ToolParameterInfo(
                name="document_id",
                param_type=ToolParamType.STRING,
                description="飞书文档 ID（取自知识库节点或文档链接）",
                required=True,
            ),
        ],
    )
    async def tool_read_document(self, document_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        """读取飞书文档正文。"""

        if error := self._guard(kwargs):
            return _err(error)
        if not document_id:
            return _err("缺少 document_id")
        settings = self._load_settings()
        try:
            content = await self.docx_get_raw_content(settings, document_id)
        except Exception as exc:  # noqa: BLE001
            return _err(f"读取飞书文档失败：{type(exc).__name__}: {exc}")
        if not content:
            return _err("文档内容为空或无法读取")
        return _ok(content[:8000], document_id=document_id, truncated=len(content) > 8000)

    # ---- 消息收发 ----

    @Tool(
        "feishu_send_message",
        brief_description="向指定飞书用户或群主动发送文本消息",
        detailed_description=(
            "用于把消息主动发给某个飞书用户（receive_id_type=open_id）或某个群（receive_id_type=chat_id）。"
            "回复当前会话请优先用 feishu_reply_message；本工具属于主动打扰，请谨慎使用。"
        ),
        parameters=[
            ToolParameterInfo(
                name="receive_id",
                param_type=ToolParamType.STRING,
                description="接收者 ID（open_id 或 chat_id）",
                required=True,
            ),
            ToolParameterInfo(
                name="receive_id_type",
                param_type=ToolParamType.STRING,
                description="ID 类型",
                required=True,
                enum_values=["open_id", "chat_id"],
            ),
            ToolParameterInfo(
                name="text",
                param_type=ToolParamType.STRING,
                description="要发送的文本内容",
                required=True,
            ),
        ],
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
            return _err(error)
        if not receive_id or not receive_id_type or not text:
            return _err("缺少 receive_id / receive_id_type / text")
        if receive_id_type not in {"open_id", "chat_id"}:
            return _err("receive_id_type 只能是 open_id 或 chat_id")
        settings = self._load_settings()
        try:
            message_id = await self.message_send_text(settings, receive_id, receive_id_type, text)
        except Exception as exc:  # noqa: BLE001
            return _err(f"发送飞书消息失败：{type(exc).__name__}: {exc}")
        return _ok(f"消息已发送，message_id={message_id or '未知'}", sent=True, message_id=message_id)

    @Tool(
        "feishu_reply_message",
        brief_description="回复某条飞书消息",
        detailed_description="回复指定 message_id 的飞书消息，形成引用回复。适合在当前会话中接话。",
        parameters=[
            ToolParameterInfo(name="message_id", param_type=ToolParamType.STRING, description="要回复的消息 ID", required=True),
            ToolParameterInfo(name="text", param_type=ToolParamType.STRING, description="回复内容", required=True),
        ],
    )
    async def tool_reply_message(self, message_id: str = "", text: str = "", **kwargs: Any) -> Dict[str, Any]:
        """回复飞书消息。"""

        if error := self._guard(kwargs):
            return _err(error)
        if not message_id or not text:
            return _err("缺少 message_id 或 text")
        settings = self._load_settings()
        try:
            new_message_id = await self.message_reply_text(settings, message_id, text)
        except Exception as exc:  # noqa: BLE001
            return _err(f"回复飞书消息失败：{type(exc).__name__}: {exc}")
        return _ok(f"已回复，message_id={new_message_id or '未知'}", sent=True, message_id=new_message_id)

    @Tool(
        "feishu_recall_message",
        brief_description="撤回一条飞书消息",
        detailed_description="撤回指定 message_id 的飞书消息。只能撤回机器人自己发送、且未超时的消息。",
        parameters=[
            ToolParameterInfo(name="message_id", param_type=ToolParamType.STRING, description="要撤回的消息 ID", required=True),
        ],
    )
    async def tool_recall_message(self, message_id: str = "", **kwargs: Any) -> Dict[str, Any]:
        """撤回飞书消息。"""

        if error := self._guard(kwargs):
            return _err(error)
        if not message_id:
            return _err("缺少 message_id")
        settings = self._load_settings()
        try:
            await self.message_recall(settings, message_id)
        except Exception as exc:  # noqa: BLE001
            return _err(f"撤回飞书消息失败：{type(exc).__name__}: {exc}")
        return _ok(f"消息 {message_id} 已撤回。", recalled=True)

    # ---- 日历 ----

    @Tool(
        "feishu_list_calendar_events",
        brief_description="按时间范围列出飞书日历日程",
        detailed_description=(
            "查询指定日历在 start_time~end_time 之间的日程。时间使用毫秒时间戳字符串。"
            "需要调用方先知道 calendar_id。"
        ),
        parameters=[
            ToolParameterInfo(name="calendar_id", param_type=ToolParamType.STRING, description="日历 ID", required=True),
            ToolParameterInfo(
                name="start_time",
                param_type=ToolParamType.STRING,
                description="开始时间（毫秒时间戳）",
                required=True,
            ),
            ToolParameterInfo(
                name="end_time",
                param_type=ToolParamType.STRING,
                description="结束时间（毫秒时间戳）",
                required=True,
            ),
        ],
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
            return _err(error)
        if not calendar_id or not start_time or not end_time:
            return _err("缺少 calendar_id / start_time / end_time")
        settings = self._load_settings()
        try:
            items = await self.calendar_list_events(settings, calendar_id, start_time, end_time)
        except Exception as exc:  # noqa: BLE001
            return _err(f"查询飞书日程失败：{type(exc).__name__}: {exc}")
        serialized = [self._serializable(item) for item in items]
        return _ok(f"该时间范围内共有 {len(serialized)} 条日程。", items=serialized)

    # ---- 审批 ----

    @Tool(
        "feishu_list_approvals",
        brief_description="按时间范围列出飞书审批实例",
        detailed_description="查询指定 approval_code 在 start_time~end_time（秒时间戳）内的审批实例列表。",
        parameters=[
            ToolParameterInfo(name="approval_code", param_type=ToolParamType.STRING, description="审批定义 code", required=True),
            ToolParameterInfo(
                name="start_time",
                param_type=ToolParamType.INTEGER,
                description="开始时间（秒时间戳）",
                required=True,
            ),
            ToolParameterInfo(
                name="end_time",
                param_type=ToolParamType.INTEGER,
                description="结束时间（秒时间戳）",
                required=True,
            ),
        ],
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
            return _err(error)
        if not approval_code:
            return _err("缺少 approval_code")
        settings = self._load_settings()
        try:
            items = await self.approval_list_instances(settings, approval_code, int(start_time), int(end_time))
        except Exception as exc:  # noqa: BLE001
            return _err(f"查询飞书审批失败：{type(exc).__name__}: {exc}")
        serialized = [self._serializable(item) for item in items]
        return _ok(f"该时间范围内共有 {len(serialized)} 条审批实例。", items=serialized)

    # ---- 多维表格 ----

    @Tool(
        "feishu_list_table_records",
        brief_description="列出飞书多维表格数据表的记录",
        detailed_description="按 app_token + table_id 读取多维表格记录，page_size 会被限制在 1~500。",
        parameters=[
            ToolParameterInfo(name="app_token", param_type=ToolParamType.STRING, description="多维表格 app_token", required=True),
            ToolParameterInfo(name="table_id", param_type=ToolParamType.STRING, description="数据表 ID", required=True),
            ToolParameterInfo(
                name="page_size",
                param_type=ToolParamType.INTEGER,
                description="返回条数上限",
                required=False,
                default=50,
            ),
        ],
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
            return _err(error)
        if not app_token or not table_id:
            return _err("缺少 app_token 或 table_id")
        settings = self._load_settings()
        try:
            items = await self.bitable_list_records(
                settings, app_token, table_id, page_size=max(1, min(int(page_size or 50), 500))
            )
        except Exception as exc:  # noqa: BLE001
            return _err(f"查询多维表格失败：{type(exc).__name__}: {exc}")
        serialized = [self._serializable(item) for item in items]
        return _ok(f"数据表返回 {len(serialized)} 条记录。", items=serialized)

    @Tool(
        "feishu_create_table_record",
        brief_description="在飞书多维表格新增一条记录",
        detailed_description=(
            "向指定数据表写入一条记录。fields 为字段名到字段值的映射，例如 {\"姓名\":\"张三\",\"状态\":\"待办\"}。"
            "字段名必须与表内字段完全一致。"
        ),
        parameters=[
            ToolParameterInfo(name="app_token", param_type=ToolParamType.STRING, description="多维表格 app_token", required=True),
            ToolParameterInfo(name="table_id", param_type=ToolParamType.STRING, description="数据表 ID", required=True),
            ToolParameterInfo(
                name="fields",
                param_type=ToolParamType.OBJECT,
                description="字段名到字段值的映射",
                required=True,
            ),
        ],
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
            return _err(error)
        if not app_token or not table_id or not fields:
            return _err("缺少 app_token / table_id / fields")
        settings = self._load_settings()
        try:
            record = await self.bitable_create_record(settings, app_token, table_id, fields)
        except Exception as exc:  # noqa: BLE001
            return _err(f"新增多维表格记录失败：{type(exc).__name__}: {exc}")
        return _ok(f"已新增记录 record_id={record.get('record_id') or '未知'}", created=record)
