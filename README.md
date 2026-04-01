# astrbot_plugin_article_summary

一个 AstrBot 插件：在群聊中识别“@机器人 + 回复消息 + 被回复内容是纯文本 URL”，自动调用 `codex` 抓取并回传 Markdown 文件 + 正文/摘要。  
插件已内置 SQLite 持久化能力：链接去重、任务状态、可继续执行、完成结果缓存复用。

## 行为说明

触发条件（当前仅 OneBot v11）：

1. 当前消息是群消息。
2. 当前消息中 `@` 了机器人。
3. 当前消息包含 `reply`。
4. 被回复内容是纯文本 URL（去掉首尾空白后仅剩一个 `http/https` 链接）。

满足条件后，插件会 `stop_event()` 并优先处理（`priority=999`）。

触发后流程：

1. 对 URL 做归一化并查 SQLite。
2. 若链接已完成抓取，直接返回缓存 Markdown 文件 + 摘要/正文。
3. 若链接为处理中/停止，直接返回状态（停止状态可继续）。
4. 若是新链接，创建任务并执行 Codex 抓取。
5. 抓取成功后写入永久缓存并标记完成，同时发布状态进入“待发布”；完成且未发布成功的记录会出现在任务列表中。插件会额外提示发布命令（群聊/私聊自动区分）、当前默认发布配置与设置命令。
6. 回传给群组的文件发送名为 `${YYYY_MM_DD}_${文章一级标题}.md`；若没有一级标题则回退为 `${YYYY_MM_DD}_article.md`。缓存源文件仍保持 `article.md` 不变。
7. 用户可直接回复“文章解析成功，可使用以下命令发布”这条引导消息触发自动发布：
   - 若默认空间/团队/知识库均已配置，直接使用默认配置发布，并向发布提示词注入 `[默认配置]`。
   - 若默认配置不满三项，需按缺项顺序在回复中补齐参数（空格分割，支持 `""` 包裹带空格内容）。
8. 抓取/继续过程中若超时或发生意外，插件会发送可解析的“任务已打断”提示（不回传详细错误）；用户可直接回复该提示（或回复“继续”）自动继续。
   - 同一群组短时间内多个任务同时中断时，会合并成一条群消息通知。
9. 发布失败时，插件会在失败消息中附带可解析标签；用户可回复该失败消息并发送“继续 <补充指令>”自动 `resume` 同一 session 重试发布。

## 指令

- `/获取文章列表`：查看当前用户的“处理中/停止/完成（仅未发布成功）”任务与状态，完成项最多展示最近 10 条。
- `/继续获取文章 <列表项id>`：继续一个停止任务，默认执行 `codex exec resume --yolo -c shell_environment_policy.inherit=all --skip-git-repo-check {session} 继续`。若当前轮结束后仍未生成 `article.md`，插件会自动基于同一 session 再继续 1 次。也可回复“任务已打断”提示消息（或回复“继续”）自动继续。
- `/发布文章 <文章ID> [空间] [团队] [知识库名称]`：发布已解析成功的文章到知识库；缺省按“空间→团队→知识库”顺序生效：传 3+ 参数按“空间/团队/知识库”解析，传 2 参数时仅在已设置默认空间时按“团队/知识库”解析，传 1 参数时仅在已设置默认空间与默认团队时按“知识库”解析，不支持跳级缺省。也支持回复发布引导消息自动触发；若发布失败可回复失败消息“继续 <补充指令>”基于同一 session 重试。每次手动 `/发布文章` 都会创建新的 publish 工作空间；若历史工作空间已丢失，会优先基于数据库/缓存重建 `article.md`，且仅历史“发布失败”会话会优先续跑，不会误用抓取会话。
- `/默认发布空间 <空间名或代号>`：设置当前用户默认发布空间。
- `/默认发布团队 <团队名或代号>`：设置当前用户默认发布团队。
- `/默认发布知识库 <知识库名或代号>`：设置当前用户默认发布知识库。
- `/默认发布 <空间> <团队> <知识库>`：一次性设置默认发布配置。
- `知识库账户 <username> <password>`：仅支持私聊。命令会先启动 Codex 验证账号有效性，验证成功后才保存凭证（密码以 Base64 编码存储）。
- `/删除文章 <文章ID[,文章ID]>`：批量删除文章记录（支持中英文逗号分隔），并清理关联缓存/工作目录（`article_file_path`、抓取/发布 run_dir、任务 run_dir）；仅创建者可删，历史数据会回退到“最早任务用户”判定创建者。路径清理带严格安全校验，危险路径会被拒绝并告警。
- `/每周总结`：统计触发时刻向前 7 天内所有用户“已发布”文章，先由 Codex 使用 `$post-article-to-xws-knowledgebase` 做链接有效性判断（仅 2xx 视为有效），再按领域输出“标题 + 访问链接”清单；链接优先使用知识库发布分享链接。
- `/文档总结帮助`：查看命令帮助。

## 生命周期

- 插件卸载/停止时，会终止正在执行的 Codex 子进程。
- 被中断任务会落库为“停止”，可通过继续命令恢复。
- “任务已打断”提示支持程序解析标签（`[AS-INTERRUPT] group=... batch=... tasks=... reason=...`），便于二次处理与自动化。

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
- `publish_resume_token_ttl_seconds`：发布失败回执 token 有效期（秒，最小 60），默认 `900`
- `default_codex_model`：默认 `gpt-5.4`
- `default_codex_reasoning_effort`：默认 `medium`
- `workspace_codex_config_path`：默认 `.codex/config.toml`
- `enable_reaction`：默认 `true`
- `reaction_emoji_id`：默认 `128064`（`👀`，沿用十进制 Unicode code point 写法；历史默认 `👍` 为 `128077`）
- `prefix`：群聊发布提示命令前缀，默认 `slfk`
- `work_root`：默认 `article-summary-runs`
- `db_path`：默认空（自动使用插件数据目录）
- `article_cache_root`：默认空（自动使用插件数据目录）
- `codex_prompt_template`：支持 `{href}`
- `codex_publish_prompt_template`：支持 `{article_path}`、`{space}`、`{team}`、`{knowledge_base}`
- `publish_trusted_domains`：发布链接可信域名白名单（逗号/空格分隔）；配置后仅白名单域名会被判为知识库链接；若你的知识库域名不包含 `xws`，建议必配
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
- 发布状态语义独立于抓取状态：抓取完成后为“待发布”，发布失败记录为“发布失败”，发布成功记录为“已发布”（仍可重复发布）。
- 若 reply 段只包含 `id`（不含正文），插件会尝试调用 OneBot `get_msg` 反查原消息，并按同一“纯文本 URL”规则判定是否触发。
- 若回复“发布引导消息”触发自动发布，且默认空间/团队/知识库已完整配置，发布提示词会额外注入：
  `[默认配置]`、`空间=...`、`团队=...`、`知识库=...`。
- 若 `codex_cmd` 是交互式（如 `codex --yolo`），插件会自动切换到 `codex_non_interactive_cmd` 执行，避免 `stdin is not a terminal`。
- 默认非交互命令会启用 `--yolo` 并继承容器环境变量（`shell_environment_policy.inherit=all`），用于避免 `bun`/本地端口监听在沙箱内被拦截；如需更严格权限，请改写这两个命令配置。
- 发送给群组的 Markdown 文件会临时重命名为 `${YYYY_MM_DD}_${文章一级标题}.md`；若标题为空或不可用，则回退为 `${YYYY_MM_DD}_article.md`。该重命名仅影响发送展示名，不修改缓存源文件路径，也不会额外截断标题。
- 抓取/继续超时或异常时，用户回执会统一为“任务已打断”简短提示，不透出详细 stderr/异常文本。
- 抓取/继续流程：若 Codex 执行超过 `codex_progress_report_seconds`（默认 120 秒），插件会分段扫描 rollout jsonl 并播报进度。
- 发布流程（`/发布文章`）：开始时先发送固定文案；若发布耗时较长，会固定每 120 秒发送进度汇总；失败时会回传失败原因与日志诊断摘要；成功时会回传文章 ID、发布目标与分享链接（若可解析）。
- `/发布文章` 会单独持久化发布态 `run_dir/session`；抓取态 `last_run_dir/last_session_id` 仅用于获取链路，不再参与发布恢复。
- 若发布时发现历史工作空间缺失，插件会优先在新的 publish 工作空间中恢复 `article.md`；`imgs/` 允许缺失，交由发布 skill 在执行期重新处理。
- 每次手动 `/发布文章` 都会创建新的 publish run dir，避免旧日志残留干扰本次分享链接识别。
- 若存在历史“发布失败” `session`，插件会优先尝试继续旧发布会话；只有在明确判定旧会话不可继续时，才会自动改为新的发布执行，以避免重复发文。
- 发布成功判定为“识别到合理知识库分享链接”；若未识别到链接，会判定发布失败并回传 `task_complete` 原文（若可读）。
- 发布提示词新增强约束：图片上传首轮失败后需至少再重试 2 次；最终输出必须包含知识库分享链接。
- 若检测到图片上传失败（如 `failed_count>0`），插件会自动基于同一 session 继续重试发布，最多 2 次。
- 发布失败消息中的恢复标识为一次性 token（非明文 session），且仅原发起用户在回复机器人失败消息并显式输入“继续/resume”时才可触发自动续跑。
- 发布链接兜底识别仅在 `xws` 域名上生效，并匹配固定路由片段；同时默认拒绝 `github/gitlab/gitee/bitbucket` 等公共代码托管域名，避免误报成功。
- 发布结果不再通过日志“任意 URL 扫描”兜底判定，避免把无关链接识别为成功链接。
- 建议在生产环境配置 `publish_trusted_domains`，将成功判定收敛到业务白名单域名。
- 每周总结流程（`/每周总结`）：分两阶段执行 Codex（均固定 `gpt-5.4` + `low`）——先做链接有效性校验，再生成按领域分组的周总结文本。
- 每周总结使用“发布分享链接”作为输出地址来源；若历史记录缺失分享链接，会尝试从发布运行日志回溯并回填。
- 账户设置流程（`知识库账户`）：会先回复“正在验证”，再启动独立 Codex 进程执行登录验证；该验证进程固定使用 `gpt-5.4` + `low`。
- 发布/验证提示词会把用户输入放入 JSON 参数块并附带安全约束，降低参数注入对提示词语义的影响。
- 进度消息格式：抓取/继续为 `[文章总结中]`（展示工具调用数、额外搜索数、累计 token 与原文地址）。
- 进度中的 `token` 取自 rollout `event_msg.token_count.info.total_token_usage.total_tokens` 的最新值。
