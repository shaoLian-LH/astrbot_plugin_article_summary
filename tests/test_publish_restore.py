from __future__ import annotations

from pathlib import Path
import shutil
import types

from repository.article_repository import (
    ARTICLE_PUBLISH_STATUS_FAILED,
    ARTICLE_PUBLISH_STATUS_PUBLISHED,
    ArticleRepository,
)
from service.article_summary_service import ArticleSummaryService


class DummyEvent:
    def __init__(self, message_id: str = "msg-1"):
        self.message_obj = types.SimpleNamespace(message_id=message_id)


def _make_repo(tmp_path: Path) -> ArticleRepository:
    return ArticleRepository(db_path=str(tmp_path / "article_summary.db"))


def _make_service(tmp_path: Path, repo: ArticleRepository) -> ArticleSummaryService:
    service = ArticleSummaryService(
        context=None,
        config={
            "work_root": str(tmp_path / "runs"),
            "article_cache_root": str(tmp_path / "article_cache"),
        },
    )
    service.article_repo = repo
    return service


def _create_completed_article(
    repo: ArticleRepository,
    article_markdown: str,
    fetch_run_dir: Path,
) -> dict:
    article = repo.create_or_get_article(
        normalized_url="https://example.com/article",
        source_url="https://example.com/article",
        owner_platform="test",
        owner_account_id="tester",
    )
    repo.set_article_completed(
        article_id=int(article["id"]),
        article_markdown=article_markdown,
        article_plain_text="plain text",
        summary_text="summary",
        article_file_path="",
        run_dir=str(fetch_run_dir),
        session_id="fetch-session",
    )
    return repo.get_article_by_id(int(article["id"])) or {}


def test_repository_publish_context_persists_and_resets(tmp_path: Path):
    repo = _make_repo(tmp_path)
    article = repo.create_or_get_article(
        normalized_url="https://example.com/repo",
        source_url="https://example.com/repo",
        owner_platform="test",
        owner_account_id="tester",
    )
    article_id = int(article["id"])

    repo.update_article_publish_context(
        article_id,
        run_dir="/tmp/publish-run",
        session_id="publish-session",
    )
    stored = repo.get_article_by_id(article_id) or {}
    assert stored["publish_last_run_dir"] == "/tmp/publish-run"
    assert stored["publish_last_session_id"] == "publish-session"

    repo.set_article_completed(
        article_id=article_id,
        article_markdown="# Title\n",
        article_plain_text="Title",
        summary_text="Title",
        article_file_path="",
        run_dir="/tmp/fetch-run",
        session_id="fetch-session",
    )
    refreshed = repo.get_article_by_id(article_id) or {}
    assert refreshed["publish_last_run_dir"] == ""
    assert refreshed["publish_last_session_id"] == ""


def test_publish_workspace_restore_uses_new_publish_dir_when_fetch_workspace_is_missing(tmp_path: Path):
    repo = _make_repo(tmp_path)
    service = _make_service(tmp_path, repo)
    fetch_run_dir = tmp_path / "fetch-run"
    fetch_run_dir.mkdir(parents=True, exist_ok=True)
    (fetch_run_dir / "article.md").write_text("# Restored\n\n![img](imgs/a.png)\n", encoding="utf-8")
    (fetch_run_dir / "imgs").mkdir(parents=True, exist_ok=True)
    (fetch_run_dir / "imgs" / "a.png").write_bytes(b"png")
    article = _create_completed_article(repo, "# Restored\n\n![img](imgs/a.png)\n", fetch_run_dir)

    cached_path = service._ensure_cached_article_file(article)
    assert cached_path is not None and cached_path.is_file()
    shutil.rmtree(fetch_run_dir)

    run_dir, article_file, restored, notice, error = service._ensure_publish_workspace(
        DummyEvent("restore-msg"),
        article,
    )

    assert error == ""
    assert restored is True
    assert run_dir is not None and run_dir.is_dir()
    assert run_dir != fetch_run_dir
    assert article_file is not None and article_file.read_text(encoding="utf-8") == "# Restored\n\n![img](imgs/a.png)\n"
    assert (run_dir / "imgs" / "a.png").is_file()
    assert "恢复 article.md" in notice

    stored = repo.get_article_by_id(int(article["id"])) or {}
    assert stored["last_run_dir"] == str(fetch_run_dir)
    assert stored["publish_last_run_dir"] == str(run_dir)
    assert stored["last_session_id"] == "fetch-session"
    assert stored["publish_last_session_id"] == ""


def test_publish_workspace_always_creates_fresh_attempt_dir(tmp_path: Path):
    repo = _make_repo(tmp_path)
    fetch_run_dir = tmp_path / "fetch-run"
    fetch_run_dir.mkdir(parents=True, exist_ok=True)
    (fetch_run_dir / "article.md").write_text("# Fresh\n\n![img](imgs/fetch.png)\n", encoding="utf-8")
    (fetch_run_dir / "imgs").mkdir(parents=True, exist_ok=True)
    (fetch_run_dir / "imgs" / "fetch.png").write_bytes(b"png")
    article = _create_completed_article(repo, "# Fresh\n\n![img](imgs/fetch.png)\n", fetch_run_dir)

    old_publish_run_dir = tmp_path / "old-publish-run"
    old_publish_run_dir.mkdir(parents=True, exist_ok=True)
    (old_publish_run_dir / "article.md").write_text("# Old publish\n", encoding="utf-8")
    (old_publish_run_dir / "codex.stdout.log").write_text(
        "分享链接: https://xws.example.com/share/old\n",
        encoding="utf-8",
    )
    repo.update_article_publish_context(
        int(article["id"]),
        run_dir=str(old_publish_run_dir),
        session_id="publish-session",
    )

    service = _make_service(tmp_path, repo)
    updated_article = repo.get_article_by_id(int(article["id"])) or {}
    run_dir, article_file, restored, notice, error = service._ensure_publish_workspace(
        DummyEvent("fresh-msg"),
        updated_article,
    )

    assert error == ""
    assert restored is False
    assert notice == ""
    assert run_dir is not None and run_dir != old_publish_run_dir
    assert article_file is not None
    assert article_file.read_text(encoding="utf-8") == "# Fresh\n\n![img](imgs/fetch.png)\n"
    assert (run_dir / "imgs" / "fetch.png").is_file()
    assert not (run_dir / "codex.stdout.log").exists()


def test_publish_workspace_uses_existing_publish_workspace_assets_when_cache_missing(tmp_path: Path):
    repo = _make_repo(tmp_path)
    service = _make_service(tmp_path, repo)
    missing_fetch_run_dir = tmp_path / "missing-fetch-run"
    article = _create_completed_article(repo, "# Publish fallback\n\n![img](imgs/publish.png)\n", missing_fetch_run_dir)

    old_publish_run_dir = tmp_path / "old-publish-run"
    old_publish_run_dir.mkdir(parents=True, exist_ok=True)
    (old_publish_run_dir / "article.md").write_text("# Publish fallback\n\n![img](imgs/publish.png)\n", encoding="utf-8")
    (old_publish_run_dir / "imgs").mkdir(parents=True, exist_ok=True)
    (old_publish_run_dir / "imgs" / "publish.png").write_bytes(b"png")
    repo.update_article_publish_context(
        int(article["id"]),
        run_dir=str(old_publish_run_dir),
        session_id="publish-session",
    )

    run_dir, article_file, restored, notice, error = service._ensure_publish_workspace(
        DummyEvent("publish-fallback-msg"),
        repo.get_article_by_id(int(article["id"])) or {},
    )

    assert error == ""
    assert restored is False
    assert notice == ""
    assert run_dir is not None and run_dir != old_publish_run_dir
    assert article_file is not None
    assert article_file.read_text(encoding="utf-8") == "# Publish fallback\n\n![img](imgs/publish.png)\n"
    assert (run_dir / "imgs" / "publish.png").is_file()


def test_publish_workspace_falls_back_to_reference_article_when_cache_is_incomplete_and_db_empty(tmp_path: Path):
    repo = _make_repo(tmp_path)
    service = _make_service(tmp_path, repo)
    missing_fetch_run_dir = tmp_path / "missing-fetch-run"
    article = _create_completed_article(repo, "# Fallback body\n\n![img](imgs/ref.png)\n", missing_fetch_run_dir)
    article_id = int(article["id"])

    cache_dir = tmp_path / "article_cache" / f"article-{article_id}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "article.md").write_text("# Broken cache\n\n![img](imgs/ref.png)\n", encoding="utf-8")

    old_publish_run_dir = tmp_path / "old-publish-run"
    old_publish_run_dir.mkdir(parents=True, exist_ok=True)
    (old_publish_run_dir / "article.md").write_text("# Fallback body\n\n![img](imgs/ref.png)\n", encoding="utf-8")
    (old_publish_run_dir / "imgs").mkdir(parents=True, exist_ok=True)
    (old_publish_run_dir / "imgs" / "ref.png").write_bytes(b"png")
    repo.update_article_publish_context(
        article_id,
        run_dir=str(old_publish_run_dir),
        session_id="publish-session",
    )

    article_for_restore = repo.get_article_by_id(article_id) or {}
    article_for_restore["article_markdown"] = ""

    run_dir, article_file, restored, notice, error = service._ensure_publish_workspace(
        DummyEvent("publish-fallback-empty-db-msg"),
        article_for_restore,
    )

    assert error == ""
    assert restored is False
    assert notice == ""
    assert run_dir is not None and run_dir != old_publish_run_dir
    assert article_file is not None
    assert article_file.read_text(encoding="utf-8") == "# Fallback body\n\n![img](imgs/ref.png)\n"
    assert (run_dir / "imgs" / "ref.png").is_file()


def test_write_article_cache_file_copies_media_artifacts(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    source_dir = tmp_path / "source-article"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_article = source_dir / "article.md"
    source_article.write_text("# Title\n\n![img](imgs/a.png)\n", encoding="utf-8")
    (source_dir / "imgs").mkdir(parents=True, exist_ok=True)
    (source_dir / "imgs" / "a.png").write_bytes(b"png")
    (source_dir / "article-captured.html").write_text("<html></html>", encoding="utf-8")

    cached_path = service._write_article_cache_file(
        123,
        "# Title\n\n![img](imgs/a.png)\n",
        source_article_file=source_article,
    )

    assert cached_path is not None and cached_path.is_file()
    assert cached_path.read_text(encoding="utf-8") == "# Title\n\n![img](imgs/a.png)\n"
    assert (cached_path.parent / "imgs" / "a.png").is_file()
    assert (cached_path.parent / "article-captured.html").is_file()


def test_validate_publish_article_assets_allows_articles_without_local_media(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    article_file = tmp_path / "article.md"
    article_file.write_text("# Title\n\nNo local images.\n", encoding="utf-8")

    assert service._validate_publish_article_assets(article_file) == ""


def test_validate_publish_article_assets_reports_missing_local_media(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    article_file = tmp_path / "article.md"
    article_file.write_text("# Title\n\n![img](imgs/missing.png)\n", encoding="utf-8")

    error = service._validate_publish_article_assets(article_file)

    assert "imgs/missing.png" in error


def test_validate_publish_article_assets_allows_markdown_image_titles(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    article_file = tmp_path / "article.md"
    imgs_dir = tmp_path / "imgs"
    imgs_dir.mkdir(parents=True, exist_ok=True)
    (imgs_dir / "ok.png").write_bytes(b"png")
    article_file.write_text('# Title\n\n![img](imgs/ok.png "caption")\n', encoding="utf-8")

    assert service._validate_publish_article_assets(article_file) == ""


def test_select_publish_resume_session_ignores_fetch_session_and_successful_publish_session(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))

    assert (
        service._select_publish_resume_session(
            {
                "publish_status": ARTICLE_PUBLISH_STATUS_FAILED,
                "last_session_id": "fetch-session",
                "publish_last_session_id": "",
            }
        )
        == ""
    )
    assert (
        service._select_publish_resume_session(
            {
                "publish_status": ARTICLE_PUBLISH_STATUS_FAILED,
                "last_session_id": "fetch-session",
                "publish_last_session_id": "publish-session",
            }
        )
        == "publish-session"
    )
    assert (
        service._select_publish_resume_session(
            {
                "publish_status": ARTICLE_PUBLISH_STATUS_PUBLISHED,
                "publish_last_session_id": "publish-session",
            }
        )
        == ""
    )


def test_resolve_publish_log_run_dir_prefers_publish_workspace(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))
    publish_run_dir = tmp_path / "publish-run"
    fetch_run_dir = tmp_path / "fetch-run"

    resolved = service._resolve_publish_log_run_dir(
        {
            "publish_last_run_dir": str(publish_run_dir),
            "last_run_dir": str(fetch_run_dir),
        }
    )

    assert resolved == publish_run_dir


def test_publish_resume_fallback_only_triggers_for_session_failures(tmp_path: Path):
    service = _make_service(tmp_path, _make_repo(tmp_path))

    assert service._looks_like_publish_resume_session_failure("session not found") is True
    assert service._looks_like_publish_resume_session_failure("会话已失效，无法恢复") is True
    assert service._looks_like_publish_resume_session_failure("未识别到知识库分享链接，发布结果不可信。") is False
