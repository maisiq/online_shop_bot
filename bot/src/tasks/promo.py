import datetime as dt
import logging
from typing import AsyncContextManager

from aiogram.enums.parse_mode import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dependency_injector.wiring import Provide, inject

from config import bot, Container
from db.models import Promo
from db.repository import Repository
from utils import escape_markdown_v2


async def notify_user(user_id, promo: Promo):
    kb = InlineKeyboardBuilder()
    kb.button(text=promo.text_link, url=promo.link)

    caption = escape_markdown_v2(promo.text)
    try:
        await bot.send_photo(
            chat_id=user_id,
            photo=promo.cover,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logging.error(str(e))


@inject
async def promote(repository: AsyncContextManager[Repository] = Provide[Container.repository]):
    cur_time = dt.datetime.now(dt.UTC)

    async with repository as repo:
        promo = await repo.get_active_promo(cur_time)

        if not promo:
            return

        logging.info('Получено новое промо, начинаю')

        async for row in repo.get_users_by_batch():
            await notify_user(row.get('id'), promo)

        logging.info('Рассылка промо выполнена, %s', promo)

        # Обновить последнее успешное выполнение и отключить рассылку
        await repo.update_promo(promo.id, cur_time)
