"""PostgreSQL helpers; transactions must remain shorter than model/build execution.

A process-level pool avoids paying a fresh TCP+TLS handshake to the managed Postgres
on every query — on slow networks that handshake dominated API latency. Connections
are checked before reuse because Supabase closes idle ones.
"""

from contextlib import contextmanager
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from lingforge.settings import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    timeout=30,
    max_idle=300,
    kwargs={"row_factory": dict_row},
    # Supabase silently drops idle connections; validate before handing one out.
    check=ConnectionPool.check_connection,
    open=True,
)


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Yield a short transaction for one state mutation or queue claim."""
    with pool.connection() as connection:
        with connection.transaction():
            yield connection
