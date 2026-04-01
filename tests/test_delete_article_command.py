from __future__ import annotations

import asyncio
from pathlib import Path
import types

import pytest

from repository.article_repository import TASK_STATUS_STOPPED, ArticleRepository
from service.article_summary_service import ArticleSummaryService


class DummyDeleteEvent:
    def __init__(
        self,
        message_str: str,
        sender_id: str = "alice",
        platform_name: str = "test",
        message_id: str = "msg-delete",
    ):
        self.message_str = message_str
        self._sender_id = sender_id
        self._platform_name = platform_name
        self.message_obj = types.SimpleNamespace(message_id=message_id)
        self.stopped = False

    def stop_event(self):
        self.stopped = True
        return self

    def plain_result(self, text: str):
        return str(text)

    def get_sender_id(self):
        return self._sender_id

    def get_platform_name(self):
        return self._platform_name

    def get_message_type(self):
        return "private"


def _make_repo(tmp_path: Path) -> ArticleRepository:
    return ArticleRepository(db_path=str(tmp_path / "article_summary.db"))


def _make_service(tmp_path: Path, repo: ArticleRepository) -> ArticleSummaryService:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    service = ArticleSummaryService(
        context=None,
        config={
            "db_path": str(tmp_path / "article_summary.db"),
            "article_cache_root": str(tmp_path / "cache"),
            "work_root": str(tmp_path / "runs"),
        },
    )
    service.article_repo = repo
    return service


def _create_article_with_artifacts(
    repo: ArticleRepository,
    tmp_path: Path,
    article_key: str,
    owner_account_id: str,
    article_file_path: Path | None = None,
) -> tuple[int, dict[str, Path]]:
    article = repo.create_or_get_article(
        normalized_url=f"https://example.com/{article_key}",
        source_url=f"https://example.com/{article_key}",
        owner_platform="test",
        owner_account_id=owner_account_id,
    )
    article_id = int(article["id"])

    cache_dir = tmp_path / "cache" / f"article-{article_id}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = article_file_path or (cache_dir / "article.md")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(f"# article-{article_id}\n", encoding="utf-8")

    fetch_run_dir = tmp_path / "runs" / f"fetch-{article_id}"
    publish_run_dir = tmp_path / "runs" / f"publish-{article_id}"
    task_run_dir = tmp_path / "runs" / f"task-{article_id}"
    fetch_run_dir.mkdir(parents=True, exist_ok=True)
    publish_run_dir.mkdir(parents=True, exist_ok=True)
    task_run_dir.mkdir(parents=True, exist_ok=True)

    repo.set_article_completed(
        article_id=article_id,
        article_markdown=f"# article-{article_id}\n",
        article_plain_text=f"article-{article_id}",
        summary_text=f"summary-{article_id}",
        article_file_path=str(cache_file),
        run_dir=str(fetch_run_dir),
        session_id=f"fetch-{article_id}",
    )
    repo.update_article_publish_context(
        article_id=article_id,
        run_dir=str(publish_run_dir),
        session_id=f"publish-{article_id}",
    )
    repo.create_task(
        platform="test",
        account_id=owner_account_id,
        article_id=article_id,
        status=TASK_STATUS_STOPPED,
        run_dir=str(task_run_dir),
        session_id=f"task-{article_id}",
    )

    return article_id, {
        "cache_dir": cache_dir,
        "cache_file": cache_file,
        "fetch_run_dir": fetch_run_dir,
        "publish_run_dir": publish_run_dir,
        "task_run_dir": task_run_dir,
    }


async def _collect_plain_results(async_gen) -> list[str]:
    results: list[str] = []
    async for item in async_gen:
        if isinstance(item, str):
            results.append(item)
    return results


def _run_async(coro):
    result = asyncio.run(coro)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    return result


def test_parse_delete_article_ids_supports_cn_comma_and_dedup(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))

    article_ids, invalid_tokens = service._parse_delete_article_ids(["1，2,2,3,abc,0"])

    assert article_ids == [1, 2, 3]
    assert invalid_tokens == ["abc", "0"]


def test_cleanup_candidate_rejects_outside_root_and_symlink(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    allowed_roots = service._resolve_delete_allowed_roots()

    outside_file = tmp_path.parent / f"{tmp_path.name}-outside" / "danger.md"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_text("danger", encoding="utf-8")

    normalized, reason = service._normalize_cleanup_candidate(outside_file, allowed_roots)
    assert normalized is None
    assert "危险路径" in reason

    symlink_path = tmp_path / "runs" / "link-path"
    symlink_target = tmp_path / "runs" / "real-path"
    symlink_target.mkdir(parents=True, exist_ok=True)
    try:
        symlink_path.symlink_to(symlink_target, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境不支持创建符号链接")

    normalized_link, reason_link = service._normalize_cleanup_candidate(symlink_path, allowed_roots)
    assert normalized_link is None
    assert "符号链接" in reason_link


def test_cleanup_candidate_rejects_path_only_under_db_parent(tmp_path: Path):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    repo = _make_repo(tmp_path)
    custom_db_parent = tmp_path / "custom-db-root"
    service = ArticleSummaryService(
        context=None,
        config={
            "db_path": str(custom_db_parent / "article_summary.db"),
            "article_cache_root": str(tmp_path / "cache"),
            "work_root": str(tmp_path / "runs"),
        },
    )
    service.article_repo = repo

    candidate = custom_db_parent / "dangerous-dir"
    candidate.mkdir(parents=True, exist_ok=True)
    allowed_roots = service._resolve_delete_allowed_roots()
    normalized, reason = service._normalize_cleanup_candidate(candidate, allowed_roots)

    assert normalized is None
    assert "危险路径" in reason


def test_delete_article_command_batch_summary_and_cleanup(tmp_path: Path):
    repo = _make_repo(tmp_path)
    service = _make_service(tmp_path, repo)

    article_id_ok, paths_ok = _create_article_with_artifacts(
        repo=repo,
        tmp_path=tmp_path,
        article_key="ok",
        owner_account_id="alice",
    )
    article_id_no_perm, _ = _create_article_with_artifacts(
        repo=repo,
        tmp_path=tmp_path,
        article_key="no-perm",
        owner_account_id="bob",
    )

    event = DummyDeleteEvent(
        message_str=f"/删除文章 {article_id_ok}，{article_id_no_perm},999,abc",
        sender_id="alice",
    )
    results = _run_async(_collect_plain_results(service.delete_article_command(event, "")))
    output = "\n".join(results)

    assert repo.get_article_by_id(article_id_ok) is None
    assert not paths_ok["cache_dir"].exists()
    assert not paths_ok["fetch_run_dir"].exists()
    assert not paths_ok["publish_run_dir"].exists()
    assert not paths_ok["task_run_dir"].exists()

    assert repo.get_article_by_id(article_id_no_perm) is not None
    assert "无效文章ID：abc" in output
    assert f"文章 {article_id_no_perm}：仅创建者可删除" in output
    assert "文章 999：未找到" in output
    assert f"文章 {article_id_ok}：已删除" in output


def test_delete_article_command_rejects_dangerous_path_cleanup(tmp_path: Path):
    repo = _make_repo(tmp_path)
    service = _make_service(tmp_path, repo)

    outside_file = tmp_path.parent / f"{tmp_path.name}-outside-2" / "danger.md"
    article_id, _ = _create_article_with_artifacts(
        repo=repo,
        tmp_path=tmp_path,
        article_key="danger-path",
        owner_account_id="alice",
        article_file_path=outside_file,
    )

    event = DummyDeleteEvent(
        message_str=f"/删除文章 {article_id}",
        sender_id="alice",
    )
    results = _run_async(_collect_plain_results(service.delete_article_command(event, "")))
    output = "\n".join(results)

    assert repo.get_article_by_id(article_id) is None
    assert outside_file.exists()
    assert "部分成功" in output
    assert "危险路径" in output
