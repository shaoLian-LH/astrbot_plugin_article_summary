from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import re
import shlex
from typing import Any, Iterable, Optional

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api import AstrBotConfig
except Exception:
    AstrBotConfig = dict  # type: ignore[misc,assignment]

URL_PATTERN = re.compile(r"https?://[^\s<>'\"\)\]]+")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^\)]+\)")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
MULTI_SPACE_PATTERN = re.compile(r"\s+")
TOML_KV_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.+?)\s*$")
CODEX_MODEL_KEYS = ("model", "default_model", "chat_model")
CODEX_REASONING_KEYS = (
    "reasoning_effort",
    "model_reasoning_effort",
    "default_reasoning_effort",
)
CODEX_SUBCOMMANDS = {
    "exec",
    "e",
    "review",
    "login",
    "logout",
    "mcp",
    "mcp-server",
    "app-server",
    "app",
    "completion",
    "sandbox",
    "debug",
    "apply",
    "a",
    "resume",
    "fork",
    "cloud",
    "features",
    "help",
}
LOG_PREVIEW_LIMIT = 240
PLUGIN_VERSION = "0.0.6"


@register(
    "astrbot_plugin_article_summary",
    "xuemufan",
    "在群聊中处理 @+reply+链接，抓取并回传 article.md 与摘要",
    PLUGIN_VERSION,
)
class ArticleSummaryPlugin(Star):
    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        self.config = config or {}

    async def initialize(self):
        logger.info(
            "[article-summary] plugin initialized, version=%s work_root=%s codex_cmd=%s",
            PLUGIN_VERSION,
            self._cfg_str("work_root", "article-summary-runs"),
            self._cfg_str("codex_cmd", "codex --yolo"),
        )

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=999)
    async def on_group_message(self, event: AstrMessageEvent):
        message_id = str(getattr(event.message_obj, "message_id", "") or "")
        platform_name = self._safe_platform_name(event)
        message_type = self._safe_message_type(event)
        sender_id = self._safe_call(event, "get_sender_id")
        group_id = self._safe_call(event, "get_group_id")
        chain_types = self._message_chain_types(event)
        logger.info(
            "[article-summary] recv id=%s platform=%s type=%s group=%s sender=%s chain=%s text=%s",
            message_id or "-",
            platform_name or "-",
            message_type or "-",
            group_id or "-",
            sender_id or "-",
            chain_types or [],
            self._preview_text(getattr(event, "message_str", "")),
        )

        if platform_name and platform_name != "aiocqhttp":
            logger.info(
                "[article-summary] skip id=%s reason=platform_mismatch platform=%s",
                message_id or "-",
                platform_name,
            )
            return

        bot_id = str(getattr(event.message_obj, "self_id", "") or "").strip()
        at_targets = self._collect_at_targets(event)
        if not self._is_at_bot(event):
            logger.info(
                "[article-summary] skip id=%s reason=not_at_bot bot_id=%s at_targets=%s",
                message_id or "-",
                bot_id or "-",
                at_targets,
            )
            return

        reply_payload = self._extract_reply_payload(event)
        if reply_payload is None:
            logger.info(
                "[article-summary] skip id=%s reason=no_reply_payload raw_type=%s",
                message_id or "-",
                type(getattr(event.message_obj, "raw_message", None)).__name__,
            )
            return

        href = self._extract_first_url(reply_payload)
        if not href:
            href = self._extract_reply_preview_url(event)

        if not href:
            reply_id = self._extract_reply_id(reply_payload)
            if reply_id:
                logger.info(
                    "[article-summary] try_get_msg id=%s reply_id=%s",
                    message_id or "-",
                    reply_id,
                )
                fetched_reply_payload = await self._fetch_reply_payload_by_id(event, reply_id)
                if fetched_reply_payload is not None:
                    href = self._extract_first_url(fetched_reply_payload)
                    logger.info(
                        "[article-summary] get_msg_result id=%s reply_id=%s url_found=%s payload_preview=%s",
                        message_id or "-",
                        reply_id,
                        bool(href),
                        self._preview_any(fetched_reply_payload),
                    )

        if not href:
            logger.info(
                "[article-summary] skip id=%s reason=reply_without_url reply_preview=%s",
                message_id or "-",
                self._preview_any(reply_payload),
            )
            return

        logger.info(
            "[article-summary] matched id=%s bot_id=%s at_targets=%s href=%s",
            message_id or "-",
            bot_id or "-",
            at_targets,
            href,
        )
        event.stop_event()
        logger.info("[article-summary] stop_event id=%s", message_id or "-")
        await self._add_recognition_reaction(event)

        run_dir = self._create_run_dir(event)
        logger.info("[article-summary] run_dir id=%s path=%s", message_id or "-", run_dir)
        prompt = self._build_codex_prompt(href)
        self._prepare_codex_workspace_config(run_dir)

        codex_error = await self._run_codex(run_dir, prompt)
        if codex_error:
            logger.warning("codex failed: %s", codex_error)
            yield event.plain_result(f"[article-summary] 处理失败: {codex_error}")
            return

        article_path = self._find_latest_article(run_dir)
        if article_path is None:
            yield event.plain_result("[article-summary] 未找到 article.md，请检查 Codex 输出。")
            return
        logger.info("[article-summary] article found id=%s path=%s", message_id or "-", article_path)

        try:
            article_markdown = article_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.exception("failed to read article.md: %s", exc)
            yield event.plain_result(f"[article-summary] 读取 article.md 失败: {exc}")
            return

        article_text = self._extract_readable_text(article_markdown)
        if not article_text:
            article_text = article_markdown.strip()
        logger.info(
            "[article-summary] article length id=%s markdown=%s plain=%s",
            message_id or "-",
            len(article_markdown),
            len(article_text),
        )

        max_plain_chars = self._cfg_int("max_plain_chars", 260)
        max_summary_chars = self._cfg_int("max_summary_chars", 320)

        if len(article_text) > max_plain_chars:
            logger.info(
                "[article-summary] summarize id=%s plain_len=%s threshold=%s max_summary=%s",
                message_id or "-",
                len(article_text),
                max_plain_chars,
                max_summary_chars,
            )
            outbound_text = await self._summarize_article(event, article_text, max_summary_chars)
            outbound_text = self._clip_text(outbound_text, max_summary_chars)
        else:
            logger.info(
                "[article-summary] send_plain id=%s plain_len=%s threshold=%s",
                message_id or "-",
                len(article_text),
                max_plain_chars,
            )
            outbound_text = self._clip_text(article_text, max_plain_chars)

        if not outbound_text:
            outbound_text = "article.md 已生成，但未能提取可发送文本。"

        yield event.chain_result([
            Comp.File(file=str(article_path), name=article_path.name),
        ])
        yield event.plain_result(outbound_text)
        logger.info("[article-summary] done id=%s", message_id or "-")

    def _cfg(self, key: str, default: Any) -> Any:
        config = self.config
        if hasattr(config, "get"):
            try:
                return config.get(key, default)
            except Exception:
                return default
        try:
            return config[key]
        except Exception:
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        value = self._cfg(key, default)
        try:
            return int(value)
        except Exception:
            return default

    def _cfg_str(self, key: str, default: str) -> str:
        value = self._cfg(key, default)
        if value is None:
            return default
        return str(value)

    def _prepare_codex_workspace_config(self, run_dir: Path) -> None:
        default_model = self._cfg_str("default_codex_model", "").strip()
        default_reasoning = self._cfg_str("default_codex_reasoning_effort", "").strip()

        workspace_model, workspace_reasoning, workspace_config_path = self._read_workspace_codex_profile()
        model = workspace_model or default_model
        reasoning = workspace_reasoning or default_reasoning

        if not model and not reasoning:
            return

        codex_dir = run_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        codex_config_path = codex_dir / "config.toml"

        lines = []
        if model:
            lines.append(f'model = "{self._toml_escape(model)}"')
        if reasoning:
            escaped = self._toml_escape(reasoning)
            lines.append(f'reasoning_effort = "{escaped}"')
            lines.append(f'model_reasoning_effort = "{escaped}"')

        codex_config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(
            "prepared codex config: model=%s reasoning=%s source=%s target=%s",
            model or "-",
            reasoning or "-",
            workspace_config_path,
            codex_config_path,
        )

    def _read_workspace_codex_profile(self) -> tuple[str, str, Path]:
        workspace_cfg_raw = self._cfg_str("workspace_codex_config_path", ".codex/config.toml").strip()
        workspace_cfg = Path(workspace_cfg_raw or ".codex/config.toml")
        if not workspace_cfg.is_absolute():
            workspace_cfg = Path.cwd() / workspace_cfg

        if not workspace_cfg.is_file():
            return "", "", workspace_cfg

        try:
            content = workspace_cfg.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("failed to read workspace codex config %s: %s", workspace_cfg, exc)
            return "", "", workspace_cfg

        kv = self._parse_toml_key_values(content)
        model = self._pick_first_nonempty(kv, CODEX_MODEL_KEYS)
        reasoning = self._pick_first_nonempty(kv, CODEX_REASONING_KEYS)
        return model, reasoning, workspace_cfg

    def _parse_toml_key_values(self, content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                continue

            match = TOML_KV_PATTERN.match(line)
            if not match:
                continue

            key = match.group(1).strip().lower()
            value = self._parse_toml_scalar(match.group(2))
            if value:
                result[key] = value
        return result

    def _parse_toml_scalar(self, raw_value: str) -> str:
        value = raw_value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        return value.strip()

    def _pick_first_nonempty(self, kv: dict[str, str], keys: Iterable[str]) -> str:
        for key in keys:
            value = kv.get(key, "").strip()
            if value:
                return value
        return ""

    def _toml_escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def _add_recognition_reaction(self, event: AstrMessageEvent) -> None:
        enabled = self._cfg("enable_reaction", True)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            logger.info("[article-summary] reaction skipped reason=disabled")
            return

        emoji_id = self._cfg_str("reaction_emoji_id", "").strip()
        if not emoji_id:
            logger.info("[article-summary] reaction skipped reason=empty_emoji_id")
            return

        message_id = getattr(event.message_obj, "message_id", None)
        if message_id is None:
            logger.info("[article-summary] reaction skipped reason=missing_message_id")
            return

        platform_name_getter = getattr(event, "get_platform_name", None)
        if callable(platform_name_getter):
            try:
                platform_name = str(platform_name_getter() or "")
                if platform_name and platform_name != "aiocqhttp":
                    logger.info(
                        "[article-summary] reaction skipped reason=platform_mismatch platform=%s",
                        platform_name,
                    )
                    return
            except Exception:
                pass

        client = getattr(event, "bot", None)
        if client is None or not hasattr(client, "api"):
            logger.info("[article-summary] reaction skipped reason=missing_bot_api")
            return

        try:
            await client.api.call_action(
                "set_msg_emoji_like",
                message_id=message_id,
                emoji_id=emoji_id,
            )
            logger.info(
                "[article-summary] reaction set message_id=%s emoji_id=%s",
                message_id,
                emoji_id,
            )
        except Exception as exc:
            logger.warning("failed to add reaction for message %s: %s", message_id, exc)

    def _is_at_bot(self, event: AstrMessageEvent) -> bool:
        bot_id = str(getattr(event.message_obj, "self_id", "") or "").strip()
        if not bot_id:
            return False

        return bot_id in self._collect_at_targets(event)

    def _extract_reply_payload(self, event: AstrMessageEvent) -> Optional[Any]:
        raw_message = getattr(event.message_obj, "raw_message", None)

        has_reply = False
        component_reply_payload: Optional[Any] = None
        segment_reply_payload: Optional[Any] = None

        for component in self._safe_get_messages(event):
            if component.__class__.__name__.lower() == "reply":
                has_reply = True
                candidate = getattr(component, "message", None)
                if candidate is not None:
                    component_reply_payload = candidate

        for segment in self._iter_message_segments(raw_message):
            if self._segment_type(segment) == "reply":
                has_reply = True
                data = self._segment_data(segment)
                if isinstance(data, dict) and data:
                    segment_reply_payload = data

        if not has_reply:
            return None

        direct_reply = self._get_field(raw_message, "reply")
        if direct_reply is not None:
            return direct_reply

        if component_reply_payload is not None:
            return component_reply_payload

        return segment_reply_payload

    def _extract_at_target(self, value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, dict):
            for key in ("qq", "user_id", "uid", "id", "target"):
                if key in value and value[key] is not None:
                    return str(value[key]).strip()
            nested = value.get("data")
            if isinstance(nested, dict):
                return self._extract_at_target(nested)
            return ""

        for attr in ("qq", "user_id", "uid", "id", "target"):
            if hasattr(value, attr):
                raw = getattr(value, attr)
                if raw is not None:
                    return str(raw).strip()

        if hasattr(value, "data"):
            return self._extract_at_target(getattr(value, "data"))

        return ""

    def _iter_message_segments(self, raw_message: Any) -> Iterable[Any]:
        if raw_message is None:
            return []

        segments = self._get_field(raw_message, "message")
        if isinstance(segments, list):
            return segments

        if isinstance(raw_message, dict):
            raw_segments = raw_message.get("message")
            if isinstance(raw_segments, list):
                return raw_segments

        if isinstance(raw_message, list):
            return raw_message

        return []

    def _segment_type(self, segment: Any) -> str:
        if isinstance(segment, dict):
            return str(segment.get("type", "") or "").strip().lower()
        return str(getattr(segment, "type", "") or "").strip().lower()

    def _segment_data(self, segment: Any) -> Any:
        if isinstance(segment, dict):
            data = segment.get("data")
            return data if data is not None else segment
        data = getattr(segment, "data", None)
        return data if data is not None else segment

    def _extract_first_url(self, payload: Any) -> str:
        for text in self._iter_text_values(payload):
            match = URL_PATTERN.search(text)
            if not match:
                continue
            url = match.group(0).rstrip(".,;!?\")'")
            return url
        return ""

    def _extract_reply_preview_url(self, event: AstrMessageEvent) -> str:
        for component in self._safe_get_messages(event):
            if component.__class__.__name__.lower() != "reply":
                continue
            for attr in ("message_str", "text", "content", "raw_message"):
                value = getattr(component, attr, None)
                if not value:
                    continue
                match = URL_PATTERN.search(str(value))
                if match:
                    return match.group(0).rstrip(".,;!?\")'")

        outline = self._safe_call(event, "get_message_outline")
        if outline:
            match = URL_PATTERN.search(outline)
            if match:
                return match.group(0).rstrip(".,;!?\")'")

        return ""

    def _extract_reply_id(self, payload: Any) -> str:
        if payload is None:
            return ""

        if isinstance(payload, dict):
            for key in ("id", "message_id", "msg_id"):
                value = payload.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            for value in payload.values():
                nested = self._extract_reply_id(value)
                if nested:
                    return nested
            return ""

        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                nested = self._extract_reply_id(item)
                if nested:
                    return nested
            return ""

        for attr in ("id", "message_id", "msg_id"):
            if hasattr(payload, attr):
                value = getattr(payload, attr)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text

        return ""

    async def _fetch_reply_payload_by_id(self, event: AstrMessageEvent, reply_id: str) -> Optional[Any]:
        client = getattr(event, "bot", None)
        if client is None or not hasattr(client, "api"):
            logger.info("[article-summary] get_msg skipped reason=missing_bot_api reply_id=%s", reply_id)
            return None

        message_id: Any = int(reply_id) if reply_id.isdigit() else reply_id
        try:
            result = await client.api.call_action(
                "get_msg",
                message_id=message_id,
            )
        except Exception as exc:
            logger.warning("[article-summary] get_msg failed reply_id=%s err=%s", reply_id, exc)
            return None

        if isinstance(result, dict) and "data" in result:
            return result.get("data")
        return result

    def _iter_text_values(self, value: Any, depth: int = 0) -> Iterable[str]:
        if depth > 8 or value is None:
            return

        if isinstance(value, str):
            if value:
                yield value
            return

        if isinstance(value, dict):
            for child in value.values():
                yield from self._iter_text_values(child, depth + 1)
            return

        if isinstance(value, (list, tuple, set)):
            for item in value:
                yield from self._iter_text_values(item, depth + 1)
            return

        if hasattr(value, "__dict__"):
            yield from self._iter_text_values(vars(value), depth + 1)
            return

        text = str(value)
        if text:
            yield text

    def _build_codex_prompt(self, href: str) -> str:
        template = self._cfg_str(
            "codex_prompt_template",
            "你需要使用 $url-to-markdown 技能去获取 {href} 的内容，如果原文是英文则还需要使用 $translate-non-zh-article 技能去进行翻译",
        )
        try:
            return template.format(href=href)
        except Exception:
            return (
                "你需要使用 $url-to-markdown 技能去获取 "
                f"{href} 的内容，如果原文是英文则还需要使用 $translate-non-zh-article 技能去进行翻译"
            )

    def _create_run_dir(self, event: AstrMessageEvent) -> Path:
        work_root_raw = self._cfg_str("work_root", "article-summary-runs").strip()
        work_root = Path(work_root_raw) if work_root_raw else Path("article-summary-runs")
        if not work_root.is_absolute():
            work_root = Path.cwd() / work_root

        message_id = self._safe_segment(str(getattr(event.message_obj, "message_id", "msg")))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = work_root / f"{timestamp}-{message_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    async def _run_codex(self, run_dir: Path, prompt: str) -> str:
        cmd_text = self._cfg_str("codex_cmd", "codex --yolo").strip() or "codex --yolo"
        timeout_seconds = self._cfg_int("codex_timeout_seconds", 900)

        try:
            args = shlex.split(cmd_text)
        except Exception as exc:
            return f"codex_cmd 配置无法解析: {exc}"

        if not args:
            return "codex_cmd 为空"

        resolved_args = self._inject_prompt(args, prompt)
        if self._looks_like_interactive_codex(resolved_args):
            fallback_args = self._build_non_interactive_codex_args(prompt)
            logger.info(
                "[article-summary] codex switch_to_non_interactive original=%s fallback=%s",
                resolved_args[:-1] if resolved_args else [],
                fallback_args[:-1] if fallback_args else [],
            )
            resolved_args = fallback_args
        logger.info(
            "[article-summary] codex exec cwd=%s cmd=%s prompt=%s",
            run_dir,
            resolved_args[:-1] if resolved_args else [],
            self._preview_text(prompt),
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *resolved_args,
                cwd=str(run_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return "未找到 codex 命令，请确认 codex 已全局安装。"
        except Exception as exc:
            return f"启动 codex 失败: {exc}"

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return f"codex 执行超时（>{timeout_seconds}s）"

        out_text = stdout.decode("utf-8", errors="ignore").strip()
        err_text = stderr.decode("utf-8", errors="ignore").strip()

        if process.returncode != 0:
            tail = err_text or out_text or "无输出"
            if len(tail) > 500:
                tail = tail[-500:]
            return f"codex 退出码 {process.returncode}: {tail}"

        if out_text:
            logger.info("codex stdout tail: %s", out_text[-500:])
        if err_text:
            logger.info("codex stderr tail: %s", err_text[-500:])

        return ""

    def _inject_prompt(self, args: list[str], prompt: str) -> list[str]:
        resolved_args = [prompt if token == "{prompt}" else token for token in args]
        if "{prompt}" not in args:
            resolved_args.append(prompt)
        return resolved_args

    def _looks_like_interactive_codex(self, args: list[str]) -> bool:
        if not args:
            return False

        if Path(args[0]).name.lower() != "codex":
            return False

        first_non_option = ""
        for token in args[1:]:
            if token.startswith("-"):
                continue
            first_non_option = token
            break

        if not first_non_option:
            return True

        return first_non_option not in CODEX_SUBCOMMANDS

    def _build_non_interactive_codex_args(self, prompt: str) -> list[str]:
        fallback_cmd = self._cfg_str(
            "codex_non_interactive_cmd",
            "codex exec --full-auto --skip-git-repo-check",
        ).strip()
        if not fallback_cmd:
            fallback_cmd = "codex exec --full-auto --skip-git-repo-check"

        try:
            fallback_base = shlex.split(fallback_cmd)
        except Exception:
            fallback_base = ["codex", "exec", "--full-auto", "--skip-git-repo-check"]

        return self._inject_prompt(fallback_base, prompt)

    def _find_latest_article(self, run_dir: Path) -> Optional[Path]:
        candidates = [
            path
            for path in run_dir.rglob("article.md")
            if path.is_file() and path.name == "article.md"
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.stat().st_mtime)

    def _extract_readable_text(self, markdown: str) -> str:
        text = markdown.strip()
        text = FRONTMATTER_PATTERN.sub("", text)
        text = CODE_BLOCK_PATTERN.sub(" ", text)
        text = INLINE_CODE_PATTERN.sub(" ", text)
        text = MARKDOWN_IMAGE_PATTERN.sub(" ", text)
        text = MARKDOWN_LINK_PATTERN.sub(r"\\1", text)
        text = HTML_TAG_PATTERN.sub(" ", text)
        text = text.replace("#", " ")
        text = text.replace("*", " ")
        text = text.replace(">", " ")
        text = MULTI_SPACE_PATTERN.sub(" ", text)
        return text.strip()

    async def _summarize_article(self, event: AstrMessageEvent, article_text: str, max_chars: int) -> str:
        input_limit = self._cfg_int("max_summary_input_chars", 12000)
        clipped_article = self._clip_text(article_text, input_limit)

        prompt_template = self._cfg_str(
            "summary_prompt_template",
            "请你将以下文章总结为不超过{max_chars}字的中文摘要，保留核心观点和关键信息。"
            "只输出摘要正文，不要输出标题或额外说明。\n\n{content}",
        )

        try:
            prompt = prompt_template.format(max_chars=max_chars, content=clipped_article)
        except Exception:
            prompt = (
                f"请你将以下文章总结为不超过{max_chars}字的中文摘要，保留核心观点和关键信息。"
                f"只输出摘要正文，不要输出标题或额外说明。\n\n{clipped_article}"
            )

        try:
            umo = event.unified_msg_origin
            provider_id = await self.context.get_current_chat_provider_id(umo=umo)
            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            summary = str(getattr(llm_resp, "completion_text", "") or "").strip()
            if summary:
                return summary
        except Exception as exc:
            logger.warning("llm summary failed, fallback to truncate: %s", exc)

        return self._clip_text(article_text, max_chars)

    def _safe_get_messages(self, event: AstrMessageEvent) -> list[Any]:
        try:
            messages = event.get_messages()
            if isinstance(messages, list):
                return messages
        except Exception:
            return []
        return []

    def _get_field(self, value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _clip_text(self, text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return text[: max_chars - 3] + "..."

    def _safe_segment(self, value: str) -> str:
        safe = re.sub(r"[^0-9A-Za-z._-]", "_", value)
        return safe[:40] or "msg"

    def _safe_call(self, event: AstrMessageEvent, method: str) -> str:
        fn = getattr(event, method, None)
        if not callable(fn):
            return ""
        try:
            value = fn()
            return str(value or "")
        except Exception:
            return ""

    def _safe_platform_name(self, event: AstrMessageEvent) -> str:
        return self._safe_call(event, "get_platform_name")

    def _safe_message_type(self, event: AstrMessageEvent) -> str:
        return self._safe_call(event, "get_message_type")

    def _message_chain_types(self, event: AstrMessageEvent) -> list[str]:
        return [message.__class__.__name__ for message in self._safe_get_messages(event)]

    def _collect_at_targets(self, event: AstrMessageEvent) -> list[str]:
        targets: list[str] = []
        for component in self._safe_get_messages(event):
            if component.__class__.__name__.lower() != "at":
                continue
            target = self._extract_at_target(component)
            if target:
                targets.append(target)

        raw_message = getattr(event.message_obj, "raw_message", None)
        for segment in self._iter_message_segments(raw_message):
            if self._segment_type(segment) != "at":
                continue
            target = self._extract_at_target(self._segment_data(segment))
            if target:
                targets.append(target)

        uniq: list[str] = []
        seen: set[str] = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            uniq.append(target)
        return uniq

    def _preview_text(self, text: str) -> str:
        if not text:
            return ""
        collapsed = MULTI_SPACE_PATTERN.sub(" ", text).strip()
        if len(collapsed) <= LOG_PREVIEW_LIMIT:
            return collapsed
        return collapsed[:LOG_PREVIEW_LIMIT] + "..."

    def _preview_any(self, value: Any) -> str:
        text = str(value)
        return self._preview_text(text)
