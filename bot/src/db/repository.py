import typing
from datetime import datetime

import psycopg
from aiogram.types import User
from psycopg.rows import dict_row

from .models import Product, Promo


class Repository(typing.Protocol):
    async def get_categories(self, page: int = 0) -> list[tuple[int, str]]: ...
    async def get_subcategories(self, category_id: int, page: int = 0): ...
    async def get_products(self, subcategory_id: int, page: int = 0) -> list[Product]: ...
    async def get_product_by_id(self, product_id: str) -> Product: ...
    async def get_active_promo(self, cur_time: datetime) -> Promo: ...
    async def get_users_by_batch(self) -> typing.AsyncGenerator[dict, None]: ...
    async def add_user(self, user: User) -> bool: ...
    async def update_promo(self, promo_id: int | str, cur_time: datetime): ...


class RawSQLRepository:
    def __init__(self, connection: psycopg.AsyncConnection):
        self._conn = connection

    async def get_categories(self, page: int = 0):
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT id, name FROM panel_category ORDER BY name")
            return await cur.fetchall()

    async def get_subcategories(self, category_id: int, page: int = 0):
        async with self._conn.cursor() as cur:
            query = '''
                SELECT id, name
                FROM panel_subcategory
                WHERE category_id = %s
                ORDER BY name
            '''
            await cur.execute(query, (category_id,))
            return await cur.fetchall()

    async def get_products(self, subcategory_id: int, page: int = 0, page_size: int = 8):
        """Получение продуктов с паджинацией для небольших таблиц"""

        offset = page * page_size
        async with self._conn.cursor(row_factory=dict_row) as cur:
            query = '''
                SELECT id, name, description, price, image
                FROM panel_product WHERE subcategory_id = %s
                ORDER BY name
                LIMIT %s
                OFFSET %s
            '''
            await cur.execute(query, (subcategory_id, page_size, offset))
            rows = await cur.fetchall()
            products = [Product.model_validate(row) for row in rows]
            return products

    async def get_product_by_id(self, product_id: str) -> Product:
        async with self._conn.cursor(row_factory=dict_row) as cur:
            query = '''
                SELECT id, name, description, price, image
                FROM panel_product WHERE id = %s
            '''
            await cur.execute(query, (product_id,))
            row = await cur.fetchone()
            return Product.model_validate(row)

    async def add_user(self, user: User) -> bool:
        async with self._conn.cursor() as cur:
            stmt = '''
                INSERT INTO panel_userbot(id, first_name, username, is_admin, is_staff)
                VALUES (%s, %s, %s, False, False)
            '''
            try:
                await cur.execute(stmt, (user.id, user.first_name, user.username))
            except psycopg.IntegrityError:
                return False
            return True

    async def get_active_promo(self, cur_time):
        promo_query = '''
            SELECT id, text, cover, link, text_link
            FROM panel_promo
            WHERE start_time <= %s AND active = True
            ORDER BY start_time
        '''
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(promo_query, (cur_time,))
            row = await cur.fetchone()

            if not row:
                return
            return Promo.model_validate(row)

    async def get_users_by_batch(self):
        async with self._conn.cursor(name="cursor1", row_factory=dict_row) as cur:
            cur.itersize = 50
            query = '''
                SELECT *
                FROM panel_userbot
            '''
            await cur.execute(query)

            async for row in cur:
                yield row

    async def update_promo(self, promo_id, cur_time):
        async with self._conn.cursor() as cur:
            stmt_promo = '''
                UPDATE panel_promo
                SET active = False, last_succeeded_at = %s
                WHERE id = %s
            '''
            await cur.execute(stmt_promo, (cur_time, promo_id))


class SQLAlchemyRepository:
    pass
