from __future__ import annotations

from pathlib import Path
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
    service = ArticleSummaryService(context=None, config={"work_root": str(tmp_path / "runs")})
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
    missing_fetch_run_dir = tmp_path / "missing-fetch-run"
    article = _create_completed_article(repo, "# Restored\nbody\n", missing_fetch_run_dir)
    service = _make_service(tmp_path, repo)

    run_dir, article_file, restored, notice, error = service._ensure_publish_workspace(
        DummyEvent("restore-msg"),
        article,
    )

    assert error == ""
    assert restored is True
    assert run_dir is not None and run_dir.is_dir()
    assert run_dir != missing_fetch_run_dir
    assert article_file is not None and article_file.read_text(encoding="utf-8") == "# Restored\nbody\n"
    assert "恢复 article.md" in notice

    stored = repo.get_article_by_id(int(article["id"])) or {}
    assert stored["last_run_dir"] == str(missing_fetch_run_dir)
    assert stored["publish_last_run_dir"] == str(run_dir)
    assert stored["last_session_id"] == "fetch-session"
    assert stored["publish_last_session_id"] == ""


def test_publish_workspace_always_creates_fresh_attempt_dir(tmp_path: Path):
    repo = _make_repo(tmp_path)
    fetch_run_dir = tmp_path / "fetch-run"
    fetch_run_dir.mkdir(parents=True, exist_ok=True)
    (fetch_run_dir / "article.md").write_text("# Fetch\n", encoding="utf-8")
    article = _create_completed_article(repo, "# Fresh\nbody\n", fetch_run_dir)

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
    assert article_file.read_text(encoding="utf-8") == "# Fresh\nbody\n"
    assert not (run_dir / "codex.stdout.log").exists()


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
