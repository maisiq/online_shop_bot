from contextlib import asynccontextmanager
from os import getenv

from psycopg_pool import AsyncConnectionPool

from .repository import RawSQLRepository

POSTGRES_CONNINFO = getenv('PAYMENTS_BOT_POSTGRES_CONNINFO')


async def init_pool():
    pool = AsyncConnectionPool(
        conninfo=POSTGRES_CONNINFO,
        min_size=1,
        max_size=10,
        open=False,
        timeout=30.0,
        max_lifetime=3600.0,
        max_idle=600.0,
    )
    return pool


@asynccontextmanager
async def get_repository(pool: AsyncConnectionPool):
    await pool.open()  # It is safe to call open() again on a pool already open
    async with pool.connection() as conn:
        repo = RawSQLRepository(conn)
        yield repo
