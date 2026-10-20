"""Database access. One SQLite connection per request, foreign keys on, explicit transactions.

Queries use `?` placeholders. A PostgreSQL port swaps the driver (psycopg) and the
placeholder style; the SQL itself is kept to the common subset on purpose.
"""
import glob
import os
import sqlite3
from contextlib import contextmanager

from flask import current_app, g


def connect(path):
    conn = sqlite3.connect(path, detect_types=0, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def all_(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def scalar(sql, params=()):
    row = get_db().execute(sql, params).fetchone()
    return None if row is None else row[0]


def run(sql, params=()):
    """Execute a write; returns lastrowid."""
    cur = get_db().execute(sql, params)
    return cur.lastrowid


@contextmanager
def transaction():
    conn = get_db()
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def migrate(path, migrations_dir):
    conn = connect(path)
    try:
        # One exclusive transaction: several worker processes may start at the same time.
        conn.execute("BEGIN EXCLUSIVE")
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
            for file in sorted(glob.glob(os.path.join(migrations_dir, "*.sql"))):
                name = os.path.basename(file)
                if name in done:
                    continue
                with open(file, encoding="utf-8") as f:
                    sql = f.read()
                # executescript() would commit implicitly, so statements run one by one.
                for statement in _split_sql(sql):
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations (name, applied_at) VALUES (?, datetime('now'))", (name,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def _split_sql(sql):
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    for part in "\n".join(lines).split(";"):
        if part.strip():
            yield part.strip()
