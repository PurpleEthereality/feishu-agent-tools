# 飞书 Agent 工具（feishu-agent-tools）

把飞书的各种能力注册为 MaiBot 的 **AI 工具**（Agent Tool），供大模型按需调用。
每个工具都带**运行期平台守卫**：只在飞书聊天中可用，非飞书聊天调用会返回「该工具仅飞书聊天可用」。

## 工具清单（10 个，覆盖 6 大能力）

| 能力 | 工具 | 说明 |
| --- | --- | --- |
| 知识库 Wiki | `feishu_search_wiki` | 按关键词搜索知识库文档节点 |
| | `feishu_list_wiki` | 列出知识库空间 / 节点 |
| 文档 docx | `feishu_read_document` | 按 document_id 读取文档纯文本正文 |
| 消息收发 | `feishu_send_message` | 给指定用户/群主动发文本消息 |
| | `feishu_reply_message` | 回复某条消息 |
| | `feishu_recall_message` | 撤回消息 |
| 日历 | `feishu_list_calendar_events` | 按时间范围列出日程 |
| 审批 | `feishu_list_approvals` | 按时间范围列出审批实例 |
| 多维表格 Base | `feishu_list_table_records` | 列出数据表记录 |
| | `feishu_create_table_record` | 新增数据表记录 |

## 权限要求

在 [飞书开放平台](https://open.feishu.cn) 为该应用开通对应权限并发布版本，且把应用加入对应资源（知识库/文档/多维表格）的成员列表：

- 知识库/文档：`wiki:wiki:readonly`、`docx:document:readonly`
- 消息：`im:message`、`im:message:send_as_bot`
- 日历：`calendar:calendar`
- 审批：`approval:approval`
- 多维表格：`bitable:app`

## 配置

复制 `config.toml.example` 为同目录下的 `config.toml`，或在 WebUI 插件配置页填写应用凭据
（与飞书适配器同一应用即可）：

```toml
[credentials]
app_id = "cli_xxx"
app_secret = "xxx"
region = "feishu"
```

> ⚠️ `config.toml` 含 App Secret，已被 `.gitignore` 忽略，请不要提交到仓库。

## 仅飞书可用（运行期守卫）

所有工具 handler 会读取调用上下文中的 `platform`，只有 `feishu` 才放行。
**拿不到平台信息时按「非飞书」处理（fail-closed）**，避免上下文缺失时绕过守卫直接调用飞书 API。
被拦截时返回「该工具仅飞书聊天可用」。

## 已知限制

- 列表类工具（知识库节点、日历日程、审批实例、多维表格记录）目前**只取首页**，
  暂不跟随 `page_token` 翻页；返回条数由参数控制并已做范围夹取。
- 本插件的 `plugin_type` 是 `extension`：它只注册 AI 工具，不是平台适配器。

## 开发

```bash
python -m pytest tests/ -q
ruff check core/ plugin.py tests/
```
