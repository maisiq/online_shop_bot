import logging
from typing import AsyncContextManager, AsyncGenerator

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import KeyboardButton, ReplyKeyboardBuilder
from config import Container, bot, dp
from db.repository import Repository
from dependency_injector.wiring import Provide, inject

router = Router()

SUBSCRIBE_TO = []


async def check_subscription(channel_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False


@router.message(CommandStart())
@inject
async def command_start_handler(
    message: Message,
    repository: AsyncContextManager[Repository] = Provide[Container.repository],
) -> None:
    if not all([check_subscription(ch, message.from_user.id) for ch in SUBSCRIBE_TO]):
        message.answer('Отсутствуют подписки на необходимые каналы')
        return

    async with repository as repo:
        await repo.add_user(message.from_user)
        logging.info('Новый пользователь @%s(%s)', message.from_user.username, message.from_user.id)

    kb = [
        [KeyboardButton(text="Каталог")],
        [KeyboardButton(text="Корзина"), KeyboardButton(text="FAQ")]
    ]

    await message.answer(
        "Привет! Нашу продукцию можно посмотреть, нажав по кнопке Каталог",
        reply_markup=ReplyKeyboardBuilder(kb).as_markup(
            resize_keyboard=True,
            input_field_placeholder="Выберите один из пунктов меню",
        )
    )