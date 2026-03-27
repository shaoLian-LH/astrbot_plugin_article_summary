from __future__ import annotations

from typing import TYPE_CHECKING

if __package__ and __package__.count(".") >= 1:
    from ..service.article_summary_service import ArticleSummaryService
else:
    from service.article_summary_service import ArticleSummaryService

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


async def handle_list_article_tasks_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
):
    async for item in ArticleSummaryService.list_article_tasks_command(plugin, event):
        yield item


async def handle_resume_article_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    item_id: str = "",
):
    async for item in ArticleSummaryService.resume_article_command(plugin, event, item_id):
        yield item


async def handle_group_message(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
):
    async for item in ArticleSummaryService.on_group_message(plugin, event):
        yield item


async def handle_article_summary_help_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
):
    async for item in ArticleSummaryService.article_summary_help_command(plugin, event):
        yield item


async def handle_weekly_summary_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
):
    async for item in ArticleSummaryService.weekly_summary_command(plugin, event):
        yield item


async def handle_set_default_publish_space_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    space_name: str = "",
):
    async for item in ArticleSummaryService.set_default_publish_space_command(
        plugin,
        event,
        space_name,
    ):
        yield item


async def handle_set_default_publish_team_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    team_name: str = "",
):
    async for item in ArticleSummaryService.set_default_publish_team_command(
        plugin,
        event,
        team_name,
    ):
        yield item


async def handle_set_default_publish_kb_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    kb_name: str = "",
):
    async for item in ArticleSummaryService.set_default_publish_kb_command(
        plugin,
        event,
        kb_name,
    ):
        yield item


async def handle_set_default_publish_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    space_name: str = "",
    team_name: str = "",
    kb_name: str = "",
):
    async for item in ArticleSummaryService.set_default_publish_command(
        plugin,
        event,
        space_name,
        team_name,
        kb_name,
    ):
        yield item


async def handle_set_knowledgebase_account_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    username: str = "",
    password: str = "",
):
    async for item in ArticleSummaryService.set_knowledgebase_account_command(
        plugin,
        event,
        username,
        password,
    ):
        yield item


async def handle_publish_article_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    article_id: str = "",
    space_name: str = "",
    team_name: str = "",
    kb_name: str = "",
):
    async for item in ArticleSummaryService.publish_article_command(
        plugin,
        event,
        article_id,
        space_name,
        team_name,
        kb_name,
    ):
        yield item


async def handle_delete_article_command(
    plugin: ArticleSummaryService,
    event: AstrMessageEvent,
    article_id: str = "",
):
    async for item in ArticleSummaryService.delete_article_command(plugin, event, article_id):
        yield item
