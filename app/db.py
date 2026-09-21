"""Acceso a datos: Postgres (Neon) en producción, SQLite en local.

Solo se usa SQL estándar y parámetros `%s`, para que valga en los dos motores.
Las fechas se guardan como texto ISO (UTC).
"""
import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.environ.get("SQLITE_PATH", str(Path(__file__).with_name("local.db")))
BLOB = "BYTEA" if IS_PG else "BLOB"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'carrusel',
        caption TEXT NOT NULL,
        hashtags TEXT NOT NULL,
        slides_text TEXT NOT NULL,
        source_url TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_at TEXT,
        published_at TEXT,
        media_id TEXT,
        permalink TEXT,
        error TEXT
    )""",
    f"""CREATE TABLE IF NOT EXISTS images (
        post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        data {BLOB} NOT NULL,
        PRIMARY KEY (post_id, position)
    )""",
    """CREATE TABLE IF NOT EXISTS kv (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by TEXT
    )""",
    # created_at: un hueco recién creado no rescata ocurrencias anteriores a su creación
    """CREATE TABLE IF NOT EXISTS schedule_slots (
        id TEXT PRIMARY KEY,
        weekday INTEGER NOT NULL,
        slot_time TEXT NOT NULL,
        kind TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (weekday, slot_time, kind)
    )""",
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def now_precise() -> str:
    """Con microsegundos: para ordenar la cola sin empates."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def connect():
    if IS_PG:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=15)
    else:
        conn = sqlite3.connect(SQLITE_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _run(conn, sql, params):
    if not IS_PG:
        sql = sql.replace("%s", "?")
    return conn.execute(sql, params)


def query(conn, sql, params=()):
    """Ejecuta y devuelve todas las filas como dicts (también con RETURNING)."""
    return [dict(r) for r in _run(conn, sql, params).fetchall()]


def one(conn, sql, params=()):
    rows = query(conn, sql, params)
    return rows[0] if rows else None


def execute(conn, sql, params=()) -> int:
    return _run(conn, sql, params).rowcount


def _has_column(conn, table: str, column: str) -> bool:
    if IS_PG:
        return bool(query(conn, (
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s"), (table, column)))
    return any(r["name"] == column for r in query(conn, f"PRAGMA table_info({table})"))


def init_db():
    with connect() as conn:
        for stmt in SCHEMA:
            execute(conn, stmt)
        # migraciones: bases de datos creadas antes de que existiera el tipo de post
        if not _has_column(conn, "posts", "kind"):
            execute(conn, "ALTER TABLE posts ADD COLUMN kind TEXT NOT NULL DEFAULT 'carrusel'")
        if not _has_column(conn, "posts", "approved_by"):
            execute(conn, "ALTER TABLE posts ADD COLUMN approved_by TEXT")


def kv_get(conn, key):
    row = one(conn, "SELECT value FROM kv WHERE key = %s", (key,))
    return row["value"] if row else None


def kv_set(conn, key, value):
    execute(conn,
            "INSERT INTO kv (key, value, updated_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now()))
