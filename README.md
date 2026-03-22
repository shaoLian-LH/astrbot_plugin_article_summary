# astrbot_plugin_article_summary

一个 AstrBot 插件：在群聊中识别“@机器人 + 回复消息 + 被回复内容含链接”，自动调用 `codex --yolo` 执行抓取与翻译工作流，并将 `article.md` + 正文/摘要发送回群。

## 行为说明

触发条件（首版仅 OneBot v11）：

1. 当前消息是群消息。
2. 当前消息中 `@` 了机器人。
3. 当前消息包含 `reply`。
4. 被回复内容中能提取到 URL。

满足上述条件后，插件会立即 `stop_event()` 停止事件传播，并以较高优先级（`priority=999`）执行，避免被其他聊天插件抢占。

触发后插件会：

1. 在运行目录创建独立工作目录。
2. 先给当前触发消息添加表情标签（可配置）。
3. 执行全局命令 `codex --yolo`（可配置），并注入提示词：
   - `你需要使用 $url-to-markdown 技能去获取 {href} 的内容，如果原文是英文则还需要使用 $translate-non-zh-article 技能去进行翻译`
4. 在本次工作目录中查找最新 `article.md`。
5. 若正文长度 `>260` 字，则通过 AstrBot provider 生成 `<=320` 字摘要。
6. 发送 `article.md` 文件 + 文本（正文或摘要）。

## 配置

插件提供 `_conf_schema.json`，可在 AstrBot 面板配置：

- `codex_cmd`：默认 `codex --yolo`
- `codex_non_interactive_cmd`：默认 `codex exec --full-auto --skip-git-repo-check`
- `codex_sessions_root`：默认 `~/.codex/sessions`
- `codex_progress_report_seconds`：默认 `120`
- `codex_progress_poll_seconds`：默认 `5`
- `codex_rollout_read_max_bytes`：默认 `524288`
- `codex_timeout_seconds`：默认 `900`
- `default_codex_model`：默认 `gpt-5.4`
- `default_codex_reasoning_effort`：默认 `medium`
- `workspace_codex_config_path`：默认 `.codex/config.toml`
- `enable_reaction`：默认 `true`
- `reaction_emoji_id`：默认 `128077`
- `work_root`：默认 `article-summary-runs`
- `codex_prompt_template`：支持 `{href}`
- `max_plain_chars`：默认 `260`
- `max_summary_chars`：默认 `320`
- `max_summary_input_chars`：默认 `12000`
- `summary_prompt_template`：支持 `{max_chars}`、`{content}`

模型与思考深度优先级：

1. 工作空间 `workspace_codex_config_path`（默认 `.codex/config.toml`）中的 `model` / `reasoning_effort`（兼容 `model_reasoning_effort`）。
2. 插件配置中的 `default_codex_model` / `default_codex_reasoning_effort`。

插件会在每次任务目录下写入 `.codex/config.toml`，再执行 `codex --yolo`，从而完成本次调用的模型/思考深度切换。

表情标签说明：

- 插件使用 OneBot API `set_msg_emoji_like` 给触发消息打标签。
- 该能力依赖协议端支持（如 NapCat）；不支持时仅记录日志，不影响主流程。

## 注意

- 需要运行环境可直接执行全局 `codex` 命令。
- 首版仅保证 OneBot v11（AIOCQHTTP）触发结构。
- 若 Codex 未产出 `article.md`，插件会直接返回错误提示。
- 触发链路调试日志统一使用前缀 `[article-summary]`，可在 AstrBot 主日志中检索该关键字。
- 若 reply 段只包含 `id`（不含正文），插件会尝试调用 OneBot `get_msg` 反查原消息再提取链接。
- 若 `codex_cmd` 是交互式（如 `codex --yolo`），插件会自动切换到 `codex_non_interactive_cmd` 执行，避免 `stdin is not a terminal`。
- 若 Codex 执行超过 `codex_progress_report_seconds`，插件会分段扫描 rollout jsonl 并播报进度（如 `web_search_call`、`function_call` 次数）。
