# Changelog

## [1.0.1] - 2026-09-14

### 细节
- 修复 `feishu_search_wiki`：搜索关键词改为放进 `SearchNodeRequestBody`，
  此前误用 `SearchNodeRequest.builder().query(...)`（该 builder 没有 `query()`），
  调用必然抛 `AttributeError`，工具完全不可用。
- 平台守卫改为 fail-closed：拿不到 `platform` 时不再放行。
- 飞书 `Client` 缓存键纳入 `app_id` / `app_secret`，修复改密钥后仍用旧凭据的问题。
- 返回条数参数做范围夹取（`limit` ≤ 50，多维表格 `page_size` ≤ 500）。
- 清单 `plugin_type` 由 `adapter` 改为 `extension`（本插件只注册 AI 工具，不是适配器）。
- 停止跟踪含 App Secret 的 `config.toml`，改为提供 `config.toml.example`。

## [1.0.0] - 2026-08-31

### 主要功能
- 新增飞书 Agent 工具插件，覆盖知识库 Wiki、文档 docx、消息收发、日历、审批、多维表格。
- 所有工具带运行期平台守卫，仅飞书聊天可用。
