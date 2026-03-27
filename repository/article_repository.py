from __future__ import annotations

import base64
import time
from typing import Iterable, Optional

if __package__ and __package__.count(".") >= 1:
    from ..infrastructure.sqlite_base import SQLiteRepositoryBase
else:
    from infrastructure.sqlite_base import SQLiteRepositoryBase


ARTICLE_STATUS_PENDING = "pending"
ARTICLE_STATUS_PROCESSING = "processing"
ARTICLE_STATUS_STOPPED = "stopped"
ARTICLE_STATUS_COMPLETED = "completed"

ARTICLE_PUBLISH_STATUS_PENDING = "pending"
ARTICLE_PUBLISH_STATUS_FAILED = "failed"
ARTICLE_PUBLISH_STATUS_PUBLISHED = "published"

TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_STOPPED = "stopped"
TASK_STATUS_COMPLETED = "completed"

_ACTIVE_TASK_STATUSES = (TASK_STATUS_PROCESSING, TASK_STATUS_STOPPED)


class ArticleRepository(SQLiteRepositoryBase):
    def _init_schema(self, conn) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_url TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                article_markdown TEXT NOT NULL DEFAULT '',
                article_plain_text TEXT NOT NULL DEFAULT '',
                summary_text TEXT NOT NULL DEFAULT '',
                article_file_path TEXT NOT NULL DEFAULT '',
                owner_platform TEXT NOT NULL DEFAULT '',
                owner_account_id TEXT NOT NULL DEFAULT '',
                publish_status TEXT NOT NULL DEFAULT 'pending',
                publish_last_error TEXT NOT NULL DEFAULT '',
                publish_updated_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                last_session_id TEXT NOT NULL DEFAULT '',
                last_run_dir TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS article_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                article_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'processing',
                run_dir TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                pid INTEGER NOT NULL DEFAULT 0,
                function_call_count INTEGER NOT NULL DEFAULT 0,
                web_search_call_count INTEGER NOT NULL DEFAULT 0,
                token_count INTEGER NOT NULL DEFAULT 0,
                progress_report_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_publish_defaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                default_space TEXT NOT NULL DEFAULT '',
                default_team TEXT NOT NULL DEFAULT '',
                default_knowledge_base TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_knowledgebase_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                password_base64 TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )

    def _ensure_columns(self, conn) -> None:
        if not self._column_exists(conn, "articles", "article_file_path"):
            conn.execute("ALTER TABLE articles ADD COLUMN article_file_path TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "owner_platform"):
            conn.execute("ALTER TABLE articles ADD COLUMN owner_platform TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "owner_account_id"):
            conn.execute("ALTER TABLE articles ADD COLUMN owner_account_id TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "publish_status"):
            conn.execute(
                "ALTER TABLE articles ADD COLUMN publish_status TEXT NOT NULL DEFAULT 'pending'",
            )
        if not self._column_exists(conn, "articles", "publish_last_error"):
            conn.execute("ALTER TABLE articles ADD COLUMN publish_last_error TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "publish_updated_at"):
            conn.execute("ALTER TABLE articles ADD COLUMN publish_updated_at INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "articles", "last_session_id"):
            conn.execute("ALTER TABLE articles ADD COLUMN last_session_id TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "last_run_dir"):
            conn.execute("ALTER TABLE articles ADD COLUMN last_run_dir TEXT NOT NULL DEFAULT ''")
        if not self._column_exists(conn, "articles", "completed_at"):
            conn.execute("ALTER TABLE articles ADD COLUMN completed_at INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "article_tasks", "pid"):
            conn.execute("ALTER TABLE article_tasks ADD COLUMN pid INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "article_tasks", "function_call_count"):
            conn.execute(
                "ALTER TABLE article_tasks ADD COLUMN function_call_count INTEGER NOT NULL DEFAULT 0",
            )
        if not self._column_exists(conn, "article_tasks", "web_search_call_count"):
            conn.execute(
                "ALTER TABLE article_tasks ADD COLUMN web_search_call_count INTEGER NOT NULL DEFAULT 0",
            )
        if not self._column_exists(conn, "article_tasks", "token_count"):
            conn.execute("ALTER TABLE article_tasks ADD COLUMN token_count INTEGER NOT NULL DEFAULT 0")
        if not self._column_exists(conn, "article_tasks", "progress_report_count"):
            conn.execute(
                "ALTER TABLE article_tasks ADD COLUMN progress_report_count INTEGER NOT NULL DEFAULT 0",
            )

    def _ensure_indexes(self, conn) -> None:
        conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_normalized_url
            ON articles(normalized_url);

            CREATE INDEX IF NOT EXISTS idx_articles_status_updated
            ON articles(status, updated_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_articles_owner
            ON articles(owner_platform, owner_account_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_articles_publish_status_updated
            ON articles(publish_status, publish_updated_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_article_tasks_owner_status_updated
            ON article_tasks(platform, account_id, status, updated_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_article_tasks_article_status_updated
            ON article_tasks(article_id, status, updated_at DESC, id DESC);

            CREATE INDEX IF NOT EXISTS idx_article_tasks_owner_article_updated
            ON article_tasks(platform, account_id, article_id, updated_at DESC, id DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_publish_defaults_owner
            ON user_publish_defaults(platform, account_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_user_kb_credentials_owner
            ON user_knowledgebase_credentials(platform, account_id);
            """
        )

    def _now(self) -> int:
        return int(time.time())

    def _to_dict(self, row) -> dict:
        return dict(row) if row is not None else {}

    def get_article_by_id(self, article_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, normalized_url, source_url, status, article_markdown, article_plain_text,
                       summary_text, article_file_path, owner_platform, owner_account_id,
                       publish_status, publish_last_error, publish_updated_at,
                       last_error, last_session_id, last_run_dir, created_at, updated_at, completed_at
                FROM articles
                WHERE id = ?
                """,
                (article_id,),
            ).fetchone()
        return self._to_dict(row) or None

    def get_article_by_url(self, normalized_url: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, normalized_url, source_url, status, article_markdown, article_plain_text,
                       summary_text, article_file_path, owner_platform, owner_account_id,
                       publish_status, publish_last_error, publish_updated_at,
                       last_error, last_session_id, last_run_dir, created_at, updated_at, completed_at
                FROM articles
                WHERE normalized_url = ?
                """,
                (normalized_url,),
            ).fetchone()
        return self._to_dict(row) or None

    def create_or_get_article(
        self,
        normalized_url: str,
        source_url: str,
        owner_platform: str = "",
        owner_account_id: str = "",
    ) -> dict:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO articles (
                    normalized_url, source_url, status, article_markdown, article_plain_text,
                    summary_text, article_file_path, owner_platform, owner_account_id,
                    publish_status, publish_last_error, publish_updated_at,
                    last_error, last_session_id, last_run_dir, created_at, updated_at, completed_at
                )
                VALUES (?, ?, 'pending', '', '', '', '', ?, ?, 'pending', '', ?, '', '', '', ?, ?, 0)
                """,
                (normalized_url, source_url, owner_platform, owner_account_id, now, now, now),
            )
            if source_url:
                conn.execute(
                    """
                    UPDATE articles
                    SET source_url = ?, updated_at = ?
                    WHERE normalized_url = ?
                    """,
                    (source_url, now, normalized_url),
                )
            row = conn.execute(
                """
                SELECT id, normalized_url, source_url, status, article_markdown, article_plain_text,
                       summary_text, article_file_path, owner_platform, owner_account_id,
                       publish_status, publish_last_error, publish_updated_at,
                       last_error, last_session_id, last_run_dir, created_at, updated_at, completed_at
                FROM articles
                WHERE normalized_url = ?
                """,
                (normalized_url,),
            ).fetchone()
        data = self._to_dict(row)
        if not data:
            raise RuntimeError("读取文章记录失败")
        return data

    def set_article_processing(
        self,
        article_id: int,
        run_dir: str = "",
        session_id: str = "",
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET status = 'processing',
                    last_run_dir = CASE WHEN ? != '' THEN ? ELSE last_run_dir END,
                    last_session_id = CASE WHEN ? != '' THEN ? ELSE last_session_id END,
                    last_error = '',
                    updated_at = ?
                WHERE id = ?
                """,
                (run_dir, run_dir, session_id, session_id, now, article_id),
            )

    def set_article_stopped(self, article_id: int, last_error: str, session_id: str = "") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET status = 'stopped',
                    last_error = ?,
                    last_session_id = CASE WHEN ? != '' THEN ? ELSE last_session_id END,
                    updated_at = ?
                WHERE id = ?
                """,
                (last_error, session_id, session_id, now, article_id),
            )

    def set_article_completed(
        self,
        article_id: int,
        article_markdown: str,
        article_plain_text: str,
        summary_text: str,
        article_file_path: str,
        run_dir: str,
        session_id: str,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET status = 'completed',
                    article_markdown = ?,
                    article_plain_text = ?,
                    summary_text = ?,
                    article_file_path = ?,
                    publish_status = ?,
                    publish_last_error = '',
                    publish_updated_at = ?,
                    last_run_dir = ?,
                    last_session_id = ?,
                    last_error = '',
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    article_markdown,
                    article_plain_text,
                    summary_text,
                    article_file_path,
                    ARTICLE_PUBLISH_STATUS_PENDING,
                    now,
                    run_dir,
                    session_id,
                    now,
                    now,
                    article_id,
                ),
            )

    def set_article_publish_failed(self, article_id: int, last_error: str) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET publish_status = ?,
                    publish_last_error = ?,
                    publish_updated_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (ARTICLE_PUBLISH_STATUS_FAILED, last_error, now, now, article_id),
            )

    def set_article_publish_pending(self, article_id: int, last_error: str = "") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET publish_status = ?,
                    publish_last_error = ?,
                    publish_updated_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (ARTICLE_PUBLISH_STATUS_PENDING, last_error, now, now, article_id),
            )

    def set_article_publish_published(self, article_id: int, last_error: str = "") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET publish_status = ?,
                    publish_last_error = ?,
                    publish_updated_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (ARTICLE_PUBLISH_STATUS_PUBLISHED, last_error, now, now, article_id),
            )

    def get_task_by_id(self, task_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, platform, account_id, article_id, status, run_dir,
                       session_id, pid, function_call_count, web_search_call_count,
                       token_count, progress_report_count, last_error, created_at, updated_at
                FROM article_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return self._to_dict(row) or None

    def get_task_by_id_for_owner(self, task_id: int, platform: str, account_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT t.id, t.platform, t.account_id, t.article_id, t.status, t.run_dir,
                       t.session_id, t.pid, t.function_call_count, t.web_search_call_count,
                       t.token_count, t.progress_report_count, t.last_error, t.created_at, t.updated_at,
                       a.normalized_url, a.source_url, a.status AS article_status,
                       a.last_session_id, a.last_error AS article_last_error,
                       a.article_markdown, a.summary_text, a.article_file_path,
                       a.owner_platform, a.owner_account_id,
                       a.publish_status, a.publish_last_error, a.publish_updated_at
                FROM article_tasks t
                JOIN articles a ON a.id = t.article_id
                WHERE t.id = ? AND t.platform = ? AND t.account_id = ?
                """,
                (task_id, platform, account_id),
            ).fetchone()
        return self._to_dict(row) or None

    def get_latest_task_for_article(
        self,
        article_id: int,
        statuses: Iterable[str] = _ACTIVE_TASK_STATUSES,
    ) -> Optional[dict]:
        status_list = [str(status).strip() for status in statuses if str(status).strip()]
        if not status_list:
            return None
        placeholders = ",".join("?" for _ in status_list)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT id, platform, account_id, article_id, status, run_dir,
                       session_id, pid, function_call_count, web_search_call_count,
                       token_count, progress_report_count, last_error, created_at, updated_at
                FROM article_tasks
                WHERE article_id = ? AND status IN ({placeholders})
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                [article_id, *status_list],
            ).fetchone()
        return self._to_dict(row) or None

    def get_latest_user_active_task_for_article(
        self,
        platform: str,
        account_id: str,
        article_id: int,
    ) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, platform, account_id, article_id, status, run_dir,
                       session_id, pid, function_call_count, web_search_call_count,
                       token_count, progress_report_count, last_error, created_at, updated_at
                FROM article_tasks
                WHERE platform = ?
                  AND account_id = ?
                  AND article_id = ?
                  AND status IN ('processing', 'stopped')
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (platform, account_id, article_id),
            ).fetchone()
        return self._to_dict(row) or None

    def get_latest_user_task_for_article(
        self,
        platform: str,
        account_id: str,
        article_id: int,
    ) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, platform, account_id, article_id, status, run_dir,
                       session_id, pid, function_call_count, web_search_call_count,
                       token_count, progress_report_count, last_error, created_at, updated_at
                FROM article_tasks
                WHERE platform = ?
                  AND account_id = ?
                  AND article_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (platform, account_id, article_id),
            ).fetchone()
        return self._to_dict(row) or None

    def create_task(
        self,
        platform: str,
        account_id: str,
        article_id: int,
        status: str,
        run_dir: str = "",
        session_id: str = "",
        pid: int = 0,
        last_error: str = "",
    ) -> dict:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO article_tasks (
                    platform, account_id, article_id, status, run_dir,
                    session_id, pid, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (platform, account_id, article_id, status, run_dir, session_id, int(pid), last_error, now, now),
            )
            task_id = int(cursor.lastrowid)

        task = self.get_task_by_id(task_id)
        if task is None:
            raise RuntimeError("读取任务记录失败")
        return task

    def update_task_status(
        self,
        task_id: int,
        status: str,
        run_dir: Optional[str] = None,
        session_id: Optional[str] = None,
        pid: Optional[int] = None,
        function_call_count: Optional[int] = None,
        web_search_call_count: Optional[int] = None,
        token_count: Optional[int] = None,
        progress_report_count: Optional[int] = None,
        last_error: Optional[str] = None,
    ) -> None:
        now = self._now()
        fields = ["status = ?", "updated_at = ?"]
        params: list[object] = [status, now]

        if run_dir is not None:
            fields.append("run_dir = ?")
            params.append(run_dir)
        if session_id is not None:
            fields.append("session_id = ?")
            params.append(session_id)
        if pid is not None:
            fields.append("pid = ?")
            params.append(int(pid))
        if function_call_count is not None:
            fields.append("function_call_count = ?")
            params.append(max(0, int(function_call_count)))
        if web_search_call_count is not None:
            fields.append("web_search_call_count = ?")
            params.append(max(0, int(web_search_call_count)))
        if token_count is not None:
            fields.append("token_count = ?")
            params.append(max(0, int(token_count)))
        if progress_report_count is not None:
            fields.append("progress_report_count = ?")
            params.append(max(0, int(progress_report_count)))
        if last_error is not None:
            fields.append("last_error = ?")
            params.append(last_error)

        params.append(task_id)
        set_sql = ", ".join(fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE article_tasks SET {set_sql} WHERE id = ?",
                params,
            )

    def update_task_rollout_stats(
        self,
        task_id: int,
        function_call_count: int,
        web_search_call_count: int,
        token_count: int,
        progress_report_count: int,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE article_tasks
                SET function_call_count = ?,
                    web_search_call_count = ?,
                    token_count = ?,
                    progress_report_count = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    max(0, int(function_call_count)),
                    max(0, int(web_search_call_count)),
                    max(0, int(token_count)),
                    max(0, int(progress_report_count)),
                    now,
                    int(task_id),
                ),
            )

    def ensure_user_task_for_article(
        self,
        platform: str,
        account_id: str,
        article_id: int,
        status: str,
        run_dir: str = "",
        session_id: str = "",
        pid: int = 0,
        last_error: str = "",
    ) -> dict:
        existing = self.get_latest_user_active_task_for_article(platform, account_id, article_id)
        if existing is None:
            return self.create_task(
                platform=platform,
                account_id=account_id,
                article_id=article_id,
                status=status,
                run_dir=run_dir,
                session_id=session_id,
                pid=pid,
                last_error=last_error,
            )

        self.update_task_status(
            existing["id"],
            status=status,
            run_dir=run_dir or existing.get("run_dir", ""),
            session_id=session_id or existing.get("session_id", ""),
            pid=int(pid),
            last_error=last_error,
        )
        refreshed = self.get_task_by_id(int(existing["id"]))
        if refreshed is None:
            raise RuntimeError("读取任务记录失败")
        return refreshed

    def ensure_user_completed_task(
        self,
        platform: str,
        account_id: str,
        article_id: int,
        run_dir: str = "",
        session_id: str = "",
    ) -> dict:
        existing = self.get_latest_user_task_for_article(platform, account_id, article_id)
        if existing is None:
            return self.create_task(
                platform=platform,
                account_id=account_id,
                article_id=article_id,
                status=TASK_STATUS_COMPLETED,
                run_dir=run_dir,
                session_id=session_id,
                pid=0,
                last_error="",
            )

        self.update_task_status(
            int(existing["id"]),
            status=TASK_STATUS_COMPLETED,
            run_dir=run_dir or str(existing.get("run_dir") or ""),
            session_id=session_id or str(existing.get("session_id") or ""),
            pid=0,
            last_error="",
        )
        refreshed = self.get_task_by_id(int(existing["id"]))
        if refreshed is None:
            raise RuntimeError("读取任务记录失败")
        return refreshed

    def complete_tasks_for_article(self, article_id: int, run_dir: str = "", session_id: str = "") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE article_tasks
                SET status = 'completed',
                    pid = 0,
                    run_dir = CASE WHEN ? != '' THEN ? ELSE run_dir END,
                    session_id = CASE WHEN ? != '' THEN ? ELSE session_id END,
                    last_error = '',
                    updated_at = ?
                WHERE article_id = ?
                  AND status IN ('processing', 'stopped')
                """,
                (run_dir, run_dir, session_id, session_id, now, article_id),
            )

    def stop_tasks_for_article(self, article_id: int, last_error: str, session_id: str = "") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE article_tasks
                SET status = 'stopped',
                    pid = 0,
                    session_id = CASE WHEN ? != '' THEN ? ELSE session_id END,
                    last_error = ?,
                    updated_at = ?
                WHERE article_id = ?
                  AND status = 'processing'
                """,
                (session_id, session_id, last_error, now, article_id),
            )

    def list_user_tasks(
        self,
        platform: str,
        account_id: str,
        statuses: Iterable[str] = (
            TASK_STATUS_PROCESSING,
            TASK_STATUS_STOPPED,
            TASK_STATUS_COMPLETED,
        ),
    ) -> list[dict]:
        status_list = [str(status).strip() for status in statuses if str(status).strip()]
        if not status_list:
            return []
        placeholders = ",".join("?" for _ in status_list)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.id, t.platform, t.account_id, t.article_id, t.status, t.run_dir,
                       t.session_id, t.pid, t.function_call_count, t.web_search_call_count,
                       t.token_count, t.progress_report_count, t.last_error, t.created_at, t.updated_at,
                       a.normalized_url, a.source_url, a.publish_status, a.publish_last_error,
                       a.publish_updated_at, a.status AS article_status
                FROM article_tasks t
                JOIN articles a ON a.id = t.article_id
                WHERE t.platform = ?
                  AND t.account_id = ?
                  AND t.status IN ({placeholders})
                ORDER BY t.updated_at DESC, t.id DESC
                """,
                [platform, account_id, *status_list],
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def list_user_pending_tasks(self, platform: str, account_id: str) -> list[dict]:
        return self.list_user_tasks(
            platform=platform,
            account_id=account_id,
            statuses=(TASK_STATUS_PROCESSING, TASK_STATUS_STOPPED),
        )

    def list_recent_published_articles(self, since_ts: int, limit: int = 200) -> list[dict]:
        max_items = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, normalized_url, source_url, status, article_markdown, article_plain_text,
                       summary_text, article_file_path, owner_platform, owner_account_id,
                       publish_status, publish_last_error, publish_updated_at,
                       last_error, last_session_id, last_run_dir, created_at, updated_at, completed_at
                FROM articles
                WHERE publish_status = ?
                  AND publish_updated_at >= ?
                ORDER BY publish_updated_at DESC, id DESC
                LIMIT ?
                """,
                (
                    ARTICLE_PUBLISH_STATUS_PUBLISHED,
                    max(0, int(since_ts)),
                    max_items,
                ),
            ).fetchall()
        return [self._to_dict(row) for row in rows]

    def get_user_publish_defaults(self, platform: str, account_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT platform, account_id, default_space, default_team, default_knowledge_base,
                       created_at, updated_at
                FROM user_publish_defaults
                WHERE platform = ? AND account_id = ?
                """,
                (platform, account_id),
            ).fetchone()
        return self._to_dict(row) or None

    def upsert_user_publish_defaults(
        self,
        platform: str,
        account_id: str,
        default_space: Optional[str] = None,
        default_team: Optional[str] = None,
        default_knowledge_base: Optional[str] = None,
    ) -> dict:
        now = self._now()
        current = self.get_user_publish_defaults(platform, account_id) or {}

        space_value = str(current.get("default_space") or "")
        team_value = str(current.get("default_team") or "")
        knowledge_base_value = str(current.get("default_knowledge_base") or "")

        if default_space is not None:
            space_value = str(default_space or "").strip()
        if default_team is not None:
            team_value = str(default_team or "").strip()
        if default_knowledge_base is not None:
            knowledge_base_value = str(default_knowledge_base or "").strip()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_publish_defaults (
                    platform, account_id, default_space, default_team,
                    default_knowledge_base, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, account_id) DO UPDATE SET
                    default_space = excluded.default_space,
                    default_team = excluded.default_team,
                    default_knowledge_base = excluded.default_knowledge_base,
                    updated_at = excluded.updated_at
                """,
                (
                    platform,
                    account_id,
                    space_value,
                    team_value,
                    knowledge_base_value,
                    int(current.get("created_at") or now),
                    now,
                ),
            )

        refreshed = self.get_user_publish_defaults(platform, account_id)
        if refreshed is None:
            raise RuntimeError("读取发布默认配置失败")
        return refreshed

    def get_user_knowledgebase_credential(self, platform: str, account_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT platform, account_id, username, password_base64,
                       created_at, updated_at
                FROM user_knowledgebase_credentials
                WHERE platform = ? AND account_id = ?
                """,
                (platform, account_id),
            ).fetchone()
        return self._to_dict(row) or None

    def upsert_user_knowledgebase_credential(
        self,
        platform: str,
        account_id: str,
        username: str,
        password_plain: str,
    ) -> dict:
        now = self._now()
        current = self.get_user_knowledgebase_credential(platform, account_id) or {}

        username_value = str(username or "").strip()
        password_base64 = base64.b64encode(str(password_plain or "").encode("utf-8")).decode("ascii")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_knowledgebase_credentials (
                    platform, account_id, username, password_base64, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, account_id) DO UPDATE SET
                    username = excluded.username,
                    password_base64 = excluded.password_base64,
                    updated_at = excluded.updated_at
                """,
                (
                    platform,
                    account_id,
                    username_value,
                    password_base64,
                    int(current.get("created_at") or now),
                    now,
                ),
            )

        refreshed = self.get_user_knowledgebase_credential(platform, account_id)
        if refreshed is None:
            raise RuntimeError("读取知识库账户凭证失败")
        return refreshed

    def resolve_article_owner(self, article_id: int) -> Optional[dict]:
        article = self.get_article_by_id(article_id)
        if article is None:
            return None

        owner_platform = str(article.get("owner_platform") or "").strip()
        owner_account_id = str(article.get("owner_account_id") or "").strip()
        if owner_platform and owner_account_id:
            return {
                "platform": owner_platform,
                "account_id": owner_account_id,
                "source": "article",
            }

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT platform, account_id
                FROM article_tasks
                WHERE article_id = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (article_id,),
            ).fetchone()
        task_owner = self._to_dict(row)
        if not task_owner:
            return None

        fallback_platform = str(task_owner.get("platform") or "").strip()
        fallback_account_id = str(task_owner.get("account_id") or "").strip()
        if not fallback_platform or not fallback_account_id:
            return None

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE articles
                SET owner_platform = CASE WHEN owner_platform = '' THEN ? ELSE owner_platform END,
                    owner_account_id = CASE WHEN owner_account_id = '' THEN ? ELSE owner_account_id END,
                    updated_at = ?
                WHERE id = ?
                """,
                (fallback_platform, fallback_account_id, self._now(), article_id),
            )

        return {
            "platform": fallback_platform,
            "account_id": fallback_account_id,
            "source": "task",
        }

    def delete_article_with_tasks(self, article_id: int) -> dict:
        with self._connect() as conn:
            task_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM article_tasks WHERE article_id = ?",
                (article_id,),
            ).fetchone()
            task_deleted = int(task_row["cnt"] or 0) if task_row is not None else 0

            conn.execute("DELETE FROM article_tasks WHERE article_id = ?", (article_id,))
            cursor = conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            article_deleted = int(cursor.rowcount or 0)

        return {
            "article_deleted": article_deleted,
            "task_deleted": task_deleted,
        }

    def stop_all_processing(self, last_error: str) -> int:
        now = self._now()
        with self._connect() as conn:
            changed = conn.execute(
                "SELECT COUNT(*) FROM article_tasks WHERE status = 'processing'",
            ).fetchone()
            total = int(changed[0] or 0) if changed is not None else 0
            if total <= 0:
                return 0
            conn.execute(
                """
                UPDATE article_tasks
                SET status = 'stopped', pid = 0, last_error = ?, updated_at = ?
                WHERE status = 'processing'
                """,
                (last_error, now),
            )
            conn.execute(
                """
                UPDATE articles
                SET status = 'stopped', last_error = ?, updated_at = ?
                WHERE status = 'processing'
                """,
                (last_error, now),
            )
        return total
