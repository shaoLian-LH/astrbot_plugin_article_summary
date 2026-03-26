from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import register

if __package__:
    from .handlers.article_handlers import (
        handle_article_summary_help_command,
        handle_delete_article_command,
        handle_group_message,
        handle_list_article_tasks_command,
        handle_publish_article_command,
        handle_resume_article_command,
        handle_set_default_publish_command,
        handle_set_default_publish_kb_command,
        handle_set_default_publish_space_command,
        handle_set_default_publish_team_command,
        handle_set_knowledgebase_account_command,
    )
    from .service.article_summary_service import ArticleSummaryService
    from .utils.constants import PLUGIN_NAME, PLUGIN_VERSION
    from .utils.filter_hooks import optional_filter_hook
else:
    from handlers.article_handlers import (
        handle_article_summary_help_command,
        handle_delete_article_command,
        handle_group_message,
        handle_list_article_tasks_command,
        handle_publish_article_command,
        handle_resume_article_command,
        handle_set_default_publish_command,
        handle_set_default_publish_kb_command,
        handle_set_default_publish_space_command,
        handle_set_default_publish_team_command,
        handle_set_knowledgebase_account_command,
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

    @filter.command("发布文章", alias={"/发布文章"})
    async def publish_article_command(
        self,
        event: AstrMessageEvent,
        article_id: str = "",
        space_name: str = "",
        team_name: str = "",
        kb_name: str = "",
    ):
        async for item in handle_publish_article_command(
            self,
            event,
            article_id,
            space_name,
            team_name,
            kb_name,
        ):
            yield item

    @filter.command("默认发布空间", alias={"/默认发布空间"})
    async def set_default_publish_space_command(self, event: AstrMessageEvent, space_name: str = ""):
        async for item in handle_set_default_publish_space_command(self, event, space_name):
            yield item

    @filter.command("默认发布团队", alias={"/默认发布团队"})
    async def set_default_publish_team_command(self, event: AstrMessageEvent, team_name: str = ""):
        async for item in handle_set_default_publish_team_command(self, event, team_name):
            yield item

    @filter.command("默认发布知识库", alias={"/默认发布知识库", "默认发布知识库"})
    async def set_default_publish_kb_command(self, event: AstrMessageEvent, kb_name: str = ""):
        async for item in handle_set_default_publish_kb_command(self, event, kb_name):
            yield item

    @filter.command("默认发布", alias={"/默认发布"})
    async def set_default_publish_command(
        self,
        event: AstrMessageEvent,
        space_name: str = "",
        team_name: str = "",
        kb_name: str = "",
    ):
        async for item in handle_set_default_publish_command(
            self,
            event,
            space_name,
            team_name,
            kb_name,
        ):
            yield item

    @filter.command("知识库账户", alias={"/知识库账户", "知识库账户"})
    async def set_knowledgebase_account_command(
        self,
        event: AstrMessageEvent,
        username: str = "",
        password: str = "",
    ):
        async for item in handle_set_knowledgebase_account_command(
            self,
            event,
            username,
            password,
        ):
            yield item

    @filter.command("删除文章", alias={"/删除文章"})
    async def delete_article_command(self, event: AstrMessageEvent, article_id: str = ""):
        async for item in handle_delete_article_command(self, event, article_id):
            yield item

    @filter.command("文档总结帮助", alias={"/文档总结帮助"})
    async def article_summary_help_command(self, event: AstrMessageEvent):
        async for item in handle_article_summary_help_command(self, event):
            yield item

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=999)
    async def on_group_message(self, event: AstrMessageEvent):
        async for item in handle_group_message(self, event):
            yield item
