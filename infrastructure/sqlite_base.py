from __future__ import annotations

import os
import sqlite3
from pathlib import Path


PLUGIN_NAME = "astrbot_plugin_article_summary"
PLUGIN_DATA_ROOT_ENV = "ARTICLE_SUMMARY_PLUGIN_DATA_ROOT"



def _is_writable_or_creatable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)

    probe = path
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            return False
        probe = parent
    return os.access(probe, os.W_OK)



def resolve_plugin_data_root() -> Path:
    override = os.getenv(PLUGIN_DATA_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    astrbot_root = Path(f"/AstrBot/data/plugin_data/{PLUGIN_NAME}")
    if _is_writable_or_creatable(astrbot_root):
        return astrbot_root

    return Path(__file__).resolve().parents[1] / ".local" / "plugin_data" / PLUGIN_NAME


DEFAULT_PLUGIN_DATA_ROOT = resolve_plugin_data_root()
DEFAULT_DB_PATH = str(DEFAULT_PLUGIN_DATA_ROOT / "article_summary.db")
DEFAULT_ARTICLE_CACHE_ROOT = str(DEFAULT_PLUGIN_DATA_ROOT / "article_cache")


class SQLiteRepositoryBase:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = str(Path(db_path).expanduser())
        self._ensure_parent_dir()
        self._init_db()

    def _ensure_parent_dir(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _column_exists(self, conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(str(row["name"] or "") == column_name for row in rows)

    def _init_db(self) -> None:
        with self._connect() as conn:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            self._init_schema(conn)
            self._ensure_columns(conn)
            self._ensure_indexes(conn)

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        del conn

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        del conn

    def _ensure_indexes(self, conn: sqlite3.Connection) -> None:
        del conn
