from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import register

if __package__:
    from .handlers.article_handlers import (
        handle_group_message,
        handle_list_article_tasks_command,
        handle_resume_article_command,
    )
    from .service.article_summary_service import ArticleSummaryService
    from .utils.constants import PLUGIN_NAME, PLUGIN_VERSION
    from .utils.filter_hooks import optional_filter_hook
else:
    from handlers.article_handlers import (
        handle_group_message,
        handle_list_article_tasks_command,
        handle_resume_article_command,
    )
    from service.article_summary_service import ArticleSummaryService
    from utils.constants import PLUGIN_NAME, PLUGIN_VERSION
    from utils.filter_hooks import optional_filter_hook


@register(
    PLUGIN_NAME,
    "xuemufan",
    "在群聊中处理 @+reply+链接，抓取并回传 article.md 与摘要",
    PLUGIN_VERSION,
)
class ArticleSummaryPlugin(ArticleSummaryService):
    @optional_filter_hook("on_plugin_unloaded")
    async def on_plugin_unloaded(self, metadata=None):
        await ArticleSummaryService.on_plugin_unloaded(self, metadata)

    @filter.command("获取文章列表", alias={"/获取文章列表"})
    async def list_article_tasks_command(self, event: AstrMessageEvent):
        async for item in handle_list_article_tasks_command(self, event):
            yield item

    @filter.command("继续获取文章", alias={"/继续获取文章"})
    async def resume_article_command(self, event: AstrMessageEvent, item_id: str = ""):
        async for item in handle_resume_article_command(self, event, item_id):
            yield item

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=999)
    async def on_group_message(self, event: AstrMessageEvent):
        async for item in handle_group_message(self, event):
            yield item
