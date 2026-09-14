"""封装飞书 OpenAPI 各功能调用（Agent 工具后端）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Tuple

from lark_oapi import Client as LarkClient
from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN
from lark_oapi.core.enum import LogLevel

from .settings import FeishuAgentToolsSettings


class _FeishuAPIError(RuntimeError):
    """飞书 API 调用错误。"""


class FeishuAgentClientMixin:
    """为 Agent 工具提供飞书各功能 API 调用能力。"""

    _client: Optional[LarkClient] = None
    _client_key: Optional[Tuple[str, str, str]] = None

    async def _ensure_client(self, settings: FeishuAgentToolsSettings) -> LarkClient:
        """按区域与凭据构造并缓存飞书 Client。

        缓存键包含 app_id / app_secret：只按区域缓存的话，用户改了密钥后
        工具仍会继续用旧凭据，直到进程重启。
        """

        domain = LARK_DOMAIN if settings.credentials.region == "lark" else FEISHU_DOMAIN
        cache_key = (domain, settings.credentials.app_id, settings.credentials.app_secret)
        if self._client is None or self._client_key != cache_key:
            self._client = (
                LarkClient.builder()
                .app_id(settings.credentials.app_id)
                .app_secret(settings.credentials.app_secret)
                .domain(domain)
                .log_level(LogLevel.WARNING)
                .build()
            )
            self._client_key = cache_key
        return self._client

    @staticmethod
    def _ensure_success(response: Any, operation: str) -> Any:
        """校验响应并返回 data。"""

        if not response.success():
            code = getattr(response, "code", None)
            msg = getattr(response, "msg", None)
            raise _FeishuAPIError(f"{operation}失败: code={code} msg={msg}")
        return response.data

    # ---- 知识库（Wiki） ----

    async def wiki_list_spaces(self, settings: FeishuAgentToolsSettings) -> List[Dict[str, Any]]:
        """列出知识库空间。"""

        from lark_oapi.api.wiki.v2 import ListSpaceRequest

        client = await self._ensure_client(settings)
        request = ListSpaceRequest.builder().page_size(50).build()
        data = self._ensure_success(await client.wiki.v2.space.alist(request), "列出知识库")
        return self._itemize(data)

    async def wiki_list_nodes(
        self,
        settings: FeishuAgentToolsSettings,
        space_id: str,
        parent_node_token: str = "",
    ) -> List[Dict[str, Any]]:
        """列出知识库空间下的节点。"""

        from lark_oapi.api.wiki.v2 import ListSpaceNodeRequest

        client = await self._ensure_client(settings)
        builder = ListSpaceNodeRequest.builder().space_id(space_id).page_size(50)
        if parent_node_token:
            builder.parent_node_token(parent_node_token)
        data = self._ensure_success(await client.wiki.v2.space_node.alist(builder.build()), "列出知识库节点")
        return self._itemize(data)

    async def wiki_search_nodes(
        self,
        settings: FeishuAgentToolsSettings,
        query: str,
        count: int = 5,
    ) -> List[Dict[str, Any]]:
        """按关键词搜索知识库节点。"""

        from lark_oapi.api.wiki.v1 import SearchNodeRequest, SearchNodeRequestBody

        client = await self._ensure_client(settings)
        # 搜索关键词要放进 request_body：SearchNodeRequest.builder() 没有 query()，
        # 之前直接 .query(query) 会抛 AttributeError，导致该工具完全不可用。
        body = SearchNodeRequestBody.builder().query(query).build()
        request = SearchNodeRequest.builder().page_size(max(1, min(int(count or 5), 50))).request_body(body).build()
        data = self._ensure_success(await client.wiki.v1.node.asearch(request), "搜索知识库")
        return self._itemize(data)

    # ---- 文档（docx） ----

    async def docx_get_raw_content(
        self,
        settings: FeishuAgentToolsSettings,
        document_id: str,
    ) -> str:
        """读取飞书文档纯文本正文。"""

        from lark_oapi.api.docx.v1 import RawContentDocumentRequest

        client = await self._ensure_client(settings)
        request = RawContentDocumentRequest.builder().document_id(document_id).build()
        data = self._ensure_success(await client.docx.v1.document.araw_content(request), "读取文档")
        content = str(data.content or "") if data is not None else ""
        return content.strip()

    # ---- 消息收发 ----

    async def message_send_text(
        self,
        settings: FeishuAgentToolsSettings,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> str:
        """给指定用户/群发送文本消息，返回 message_id。"""

        from lark_oapi.api.im.v1 import CreateMessageRequestBody, CreateMessageRequest

        client = await self._ensure_client(settings)
        body = CreateMessageRequestBody.builder().receive_id(receive_id).msg_type("text").content(
            json.dumps({"text": text}, ensure_ascii=False)
        )
        request = CreateMessageRequest.builder().receive_id_type(receive_id_type).request_body(body.build()).build()
        data = self._ensure_success(await client.im.v1.message.acreate(request), "发送消息")
        return str(data.message_id or "") if data is not None else ""

    async def message_reply_text(
        self,
        settings: FeishuAgentToolsSettings,
        message_id: str,
        text: str,
    ) -> str:
        """回复某条飞书消息，返回新消息 message_id。"""

        from lark_oapi.api.im.v1 import CreateMessageRequestBody, ReplyMessageRequest

        client = await self._ensure_client(settings)
        body = CreateMessageRequestBody.builder().msg_type("text").content(
            json.dumps({"text": text}, ensure_ascii=False)
        )
        request = ReplyMessageRequest.builder().message_id(message_id).request_body(body.build()).build()
        data = self._ensure_success(await client.im.v1.message.areply(request), "回复消息")
        return str(data.message_id or "") if data is not None else ""

    async def message_recall(self, settings: FeishuAgentToolsSettings, message_id: str) -> bool:
        """撤回一条飞书消息。"""

        from lark_oapi.api.im.v1 import DeleteMessageRequest

        client = await self._ensure_client(settings)
        request = DeleteMessageRequest.builder().message_id(message_id).build()
        response = await client.im.v1.message.adelete(request)
        # 撤回接口响应不含 data 字段，仅校验业务码。
        if not response.success():
            raise _FeishuAPIError(f"撤回消息失败: code={response.code} msg={response.msg}")
        return True

    # ---- 日历 ----

    async def calendar_list_events(
        self,
        settings: FeishuAgentToolsSettings,
        calendar_id: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict[str, Any]]:
        """按时间范围列出日历日程。"""

        from lark_oapi.api.calendar.v4 import ListCalendarEventRequest

        client = await self._ensure_client(settings)
        request = (
            ListCalendarEventRequest.builder()
            .calendar_id(calendar_id)
            .start_time(start_time)
            .end_time(end_time)
            .page_size(50)
            .build()
        )
        data = self._ensure_success(await client.calendar.v4.calendar_event.alist(request), "查询日程")
        return self._itemize(data)

    # ---- 审批 ----

    async def approval_list_instances(
        self,
        settings: FeishuAgentToolsSettings,
        approval_code: str,
        start_time: int,
        end_time: int,
    ) -> List[Dict[str, Any]]:
        """按时间范围列出审批实例。"""

        from lark_oapi.api.approval.v4 import ListInstanceRequest

        client = await self._ensure_client(settings)
        request = (
            ListInstanceRequest.builder()
            .approval_code(approval_code)
            .start_time(start_time)
            .end_time(end_time)
            .page_size(50)
            .build()
        )
        data = self._ensure_success(await client.approval.v4.instance.alist(request), "查询审批")
        return self._itemize(data)

    # ---- 多维表格（Base） ----

    async def bitable_list_records(
        self,
        settings: FeishuAgentToolsSettings,
        app_token: str,
        table_id: str,
        page_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出多维表格数据表的记录。"""

        from lark_oapi.api.bitable.v1 import ListAppTableRecordRequest

        client = await self._ensure_client(settings)
        request = (
            ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(page_size)
            .build()
        )
        data = self._ensure_success(await client.bitable.v1.app_table_record.alist(request), "查询多维表格")
        return self._itemize(data)

    async def bitable_create_record(
        self,
        settings: FeishuAgentToolsSettings,
        app_token: str,
        table_id: str,
        fields: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """在多维表格数据表新增一条记录。"""

        from lark_oapi.api.bitable.v1 import CreateAppTableRecordRequestBody, CreateAppTableRecordRequest

        client = await self._ensure_client(settings)
        body = CreateAppTableRecordRequestBody.builder().fields(dict(fields))
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .request_body(body.build())
            .build()
        )
        data = self._ensure_success(await client.bitable.v1.app_table_record.acreate(request), "新增多维表格记录")
        return {"record_id": str(data.record_id or "") if data is not None else "", "fields": dict(fields)}

    # ---- 通用 ----

    @staticmethod
    def _itemize(data: Any) -> List[Dict[str, Any]]:
        """从分页响应中提取 items 列表。"""

        items = getattr(data, "items", None) if data is not None else None
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
        return []

    @staticmethod
    def _serializable(value: Any) -> Any:
        """把 lark 模型对象转成可 JSON 化的 dict。"""

        if isinstance(value, Mapping):
            return {key: FeishuAgentClientMixin._serializable(val) for key, val in value.items()}
        if isinstance(value, list):
            return [FeishuAgentClientMixin._serializable(item) for item in value]
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return value
