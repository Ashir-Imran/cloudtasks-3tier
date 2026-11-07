"""PostgreSQL access: connection pool + versioned migrations."""
import logging
import os
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger("db")
_pool = None


def _conn_kwargs():
    # Credentials come ONLY from environment variables (Secrets Manager on AWS)
    return dict(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "tasksdb"),
        user=os.environ.get("DB_USER", "appuser"),
        password=os.environ.get("DB_PASSWORD", ""),
        connect_timeout=5,
    )


def get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, int(os.environ.get("DB_POOL_MAX", "10")), **_conn_kwargs())
    return _pool


@contextmanager
def cursor(dict_rows=True):
    """Yield a cursor inside a transaction; commit on success, rollback on error."""
    pool = get_pool()
    conn = pool.getconn()
    broken = False
    try:
        factory = psycopg2.extras.RealDictCursor if dict_rows else None
        with conn.cursor(cursor_factory=factory) as cur:
            yield cur
        conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        broken = True  # e.g. RDS failover: drop this connection from the pool
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn, close=broken)


MIGRATIONS = [
    (1, """
    CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        name VARCHAR(100) NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE TABLE tasks (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title VARCHAR(200) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        priority SMALLINT NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
        status VARCHAR(20) NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in_progress','done')),
        due_date DATE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX idx_tasks_user_status ON tasks (user_id, status);
    CREATE INDEX idx_tasks_user_due ON tasks (user_id, due_date);
    CREATE TABLE attachments (
        id SERIAL PRIMARY KEY,
        task_id INT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        filename VARCHAR(255) NOT NULL,
        s3_key TEXT NOT NULL,
        content_type VARCHAR(100) NOT NULL,
        size_bytes INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    CREATE INDEX idx_attachments_task ON attachments (task_id);
    """),
]


def migrate(retries=15, delay=3):
    """Apply pending migrations. An advisory lock makes this safe when several
    instances (Auto Scaling) start at the same time."""
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(**_conn_kwargs())
        except psycopg2.OperationalError as exc:
            log.warning("DB not ready (attempt %s/%s): %s", attempt, retries, str(exc).strip())
            time.sleep(delay)
            continue
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(727001)")
                cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                                 version INT PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT NOW())""")
                cur.execute("SELECT version FROM schema_migrations")
                applied = {r[0] for r in cur.fetchall()}
                for version, sql in MIGRATIONS:
                    if version not in applied:
                        log.info("applying migration %s", version)
                        cur.execute(sql)
                        cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            conn.commit()
            log.info("database ready")
            return
        finally:
            conn.close()
    raise RuntimeError("database not reachable, giving up")
