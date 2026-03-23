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
