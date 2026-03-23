# astrbot_plugin_article_summary

一个 AstrBot 插件：在群聊中识别“@机器人 + 回复消息 + 被回复内容含链接”，自动调用 `codex` 抓取并回传 `article.md` + 正文/摘要。  
插件已内置 SQLite 持久化能力：链接去重、任务状态、可继续执行、完成结果缓存复用。

## 行为说明

触发条件（当前仅 OneBot v11）：

1. 当前消息是群消息。
2. 当前消息中 `@` 了机器人。
3. 当前消息包含 `reply`。
4. 被回复内容中能提取到 URL。

满足条件后，插件会 `stop_event()` 并优先处理（`priority=999`）。

触发后流程：

1. 对 URL 做归一化并查 SQLite。
2. 若链接已完成抓取，直接返回缓存 `article.md` + 摘要/正文。
3. 若链接为处理中/停止，直接返回状态（停止状态可继续）。
4. 若是新链接，创建任务并执行 Codex 抓取。
5. 抓取成功后写入永久缓存并标记完成；完成项不会出现在任务列表中。

## 指令

- `/获取文章列表`：查看当前用户的“处理中/停止”任务与状态。
- `/继续获取文章 <列表项id>`：继续一个停止任务，默认执行 `codex exec resume --yolo -c shell_environment_policy.inherit=all --skip-git-repo-check {session} 继续`。

## 生命周期

- 插件卸载/停止时，会终止正在执行的 Codex 子进程。
- 被中断任务会落库为“停止”，可通过继续命令恢复。

## 配置

插件提供 `_conf_schema.json`，可在 AstrBot 面板配置：

- `codex_cmd`：默认 `codex --yolo`
- `codex_non_interactive_cmd`：默认 `codex exec --yolo -c shell_environment_policy.inherit=all --skip-git-repo-check`
- `codex_resume_cmd_template`：默认 `codex exec resume --yolo -c shell_environment_policy.inherit=all --skip-git-repo-check {session} 继续`
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
- `db_path`：默认空（自动使用插件数据目录）
- `article_cache_root`：默认空（自动使用插件数据目录）
- `codex_prompt_template`：支持 `{href}`
- `max_plain_chars`：默认 `260`
- `max_summary_chars`：默认 `320`
- `max_summary_input_chars`：默认 `12000`
- `summary_prompt_template`：支持 `{max_chars}`、`{content}`

模型与思考深度优先级：

1. 工作空间 `workspace_codex_config_path`（默认 `.codex/config.toml`）中的 `model` / `reasoning_effort`（兼容 `model_reasoning_effort`）。
2. 插件配置中的 `default_codex_model` / `default_codex_reasoning_effort`。

## 注意

- 需要运行环境可直接执行全局 `codex` 命令。
- 同链接文章会永久保存在数据库，后续用户请求可直接复用。
- 若 reply 段只包含 `id`（不含正文），插件会尝试调用 OneBot `get_msg` 反查原消息再提取链接。
- 若 `codex_cmd` 是交互式（如 `codex --yolo`），插件会自动切换到 `codex_non_interactive_cmd` 执行，避免 `stdin is not a terminal`。
- 默认非交互命令会启用 `--yolo` 并继承容器环境变量（`shell_environment_policy.inherit=all`），用于避免 `bun`/本地端口监听在沙箱内被拦截；如需更严格权限，请改写这两个命令配置。
- 若 Codex 执行超过 `codex_progress_report_seconds`，插件会分段扫描 rollout jsonl 并播报进度。
