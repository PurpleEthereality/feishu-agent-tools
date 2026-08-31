"""定义飞书 Agent 工具插件配置。"""

from __future__ import annotations

from typing import Any, ClassVar

from maibot_sdk import Field, PluginConfigBase
from pydantic import field_validator

from .constants import SUPPORTED_CONFIG_VERSION


class PluginSection(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用飞书 Agent 工具插件。",
        json_schema_extra={"label": "启用插件", "order": 0},
    )
    config_version: str = Field(
        default=SUPPORTED_CONFIG_VERSION,
        description="当前配置结构版本。",
        json_schema_extra={"disabled": True, "hidden": True, "label": "配置版本", "order": 99},
    )


class CredentialsSection(PluginConfigBase):
    """飞书开放平台凭据配置。"""

    __ui_label__: ClassVar[str] = "机器人凭据"
    __ui_order__: ClassVar[int] = 1

    app_id: str = Field(
        default="",
        max_length=128,
        description="飞书开放平台自建应用 App ID。",
        json_schema_extra={"label": "App ID", "order": 0},
    )
    app_secret: str = Field(
        default="",
        max_length=512,
        description="飞书开放平台自建应用 App Secret。",
        json_schema_extra={"label": "App Secret", "input_type": "password", "order": 1},
    )
    region: str = Field(
        default="feishu",
        description="开放平台区域：feishu 或 lark。",
        json_schema_extra={"label": "区域", "options": ["feishu", "lark"], "order": 2},
    )

    @field_validator("app_id", "app_secret", mode="before")
    @classmethod
    def _normalize_credentials(cls, value: Any) -> str:
        """规范化凭据文本。"""

        if not isinstance(value, str):
            raise ValueError("飞书凭据必须是字符串")
        return value.strip()


class FeishuAgentToolsSettings(PluginConfigBase):
    """飞书 Agent 工具插件完整配置。"""

    plugin: PluginSection = Field(default_factory=PluginSection)
    credentials: CredentialsSection = Field(default_factory=CredentialsSection)

    def should_connect(self) -> bool:
        """判断当前配置是否应该启用。"""

        return self.plugin.enabled
