from typing import AsyncContextManager

from aiogram import F, Router
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from dependency_injector.wiring import Provide, inject

from cart.cart import Cart
from config import Container
from db.repository import Repository
from utils import are_keyboards_equal, escape_markdown_v2


router = Router()


# Pagination

class PaginationState(StatesGroup):
    category = State()
    subcategory = State()
    product = State()


@inject
async def get_items_by_state(
    data: dict,
    cur_state: State,
    repository: AsyncContextManager[Repository] = Provide[Container.repository],
):
    items = []
    async with repository as repo:
        match cur_state:
            case PaginationState.category:
                items = await repo.get_categories()
            case PaginationState.subcategory:
                items = await repo.get_subcategories(data['category'])
            case PaginationState.product:
                items = await repo.get_products(data['subcategory'])
            case _:
                raise ValueError('Bad current state: ', cur_state)
    return items


async def get_paginated_builder(state: FSMContext, page: int, items_per_page: int = 6):
    data = await state.get_data()
    cur_state = await state.get_state()
    data_type = cur_state.split(':')[1]

    items = await get_items_by_state(data, cur_state)

    if not items:
        return

    start = page * items_per_page
    end = start + items_per_page
    show_items = items[start:end]

    builder = InlineKeyboardBuilder()

    for item in show_items:
        if data_type == 'product':
            builder.button(text=item.name, callback_data=f'{data_type}_{str(item.id)}')
        else:
            builder.button(text=item[1], callback_data=f'{data_type}_{item[0]}')

    if cur_state == PaginationState.subcategory:
        builder.button(text='↩️ Вернуться', callback_data='catalog')
    elif cur_state == PaginationState.product:
        category = data['category']
        builder.button(text='↩️ Вернуться', callback_data=f'category_{category}')

    if page > 0:
        builder.button(text="⬅️ Назад", callback_data="prev_page")
    if end < len(items):
        builder.button(text="Вперед ➡️", callback_data="next_page")

    adjust_items = [2] * int(len(items) / 2)  # [n] columns * number of rows
    builder.adjust(*adjust_items, 1, 2)

    return builder


@router.callback_query(F.data.in_(['prev_page', 'next_page']))
async def switch_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if callback.data == 'prev_page':
        page = data['page'] - 1
    elif callback.data == 'next_page':
        page = data['page'] + 1

    await state.update_data(page=page)
    builder = await get_paginated_builder(state, page)

    await callback.message.edit_reply_markup(callback.inline_message_id, reply_markup=builder.as_markup())
    await callback.answer()


# Handlers

@router.message(F.text.lower() == 'каталог')
async def catalog_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(PaginationState.category)
    page = 0

    if builder := await get_paginated_builder(state, page):
        await state.update_data(page=page)
        await message.answer('Выберите категорию:', reply_markup=builder.as_markup())
    else:
        await message.answer('Тут пока ничего нет 😢')


def get_product_in_cart_nav_keyboard(product_id, cart):
    kb = [
        [InlineKeyboardButton(text=f'В корзине: {cart[product_id]['quantity']} шт.', callback_data='product-info')],
        [InlineKeyboardButton(text='+', callback_data=f'product-cart_plus_{product_id}'),
         InlineKeyboardButton(text='-', callback_data=f'product-cart_minus_{product_id}')],
        [InlineKeyboardButton(text='Убрать из корзины', callback_data=f'product-cart_delete_{product_id}')]
    ]
    return kb


@router.callback_query(F.data.startswith("product_"))
@inject
async def product_detail_handler(
    callback: CallbackQuery,
    state: FSMContext,
    repository: AsyncContextManager[Repository] = Provide[Container.repository],
):
    cart = await Cart().init(state)
    product_id = callback.data.split("_")[1]

    async with repository as repo:
        product = await repo.get_product_by_id(product_id)

    kb = []

    if product_id in cart:
        kb = get_product_in_cart_nav_keyboard(product_id, cart)
    else:
        kb.append([InlineKeyboardButton(text='Добавить в корзину', callback_data=f'product-cart_add_{product_id}')])
    builder = InlineKeyboardBuilder(kb)

    base_caption = (
        f'Название: {product.name}\n'
        f'Описание: {product.description}\n'
        f'Стоимость: {str(product.price)} руб.\n'
    )
    caption = escape_markdown_v2(base_caption)

    await callback.message.bot.send_photo(
        callback.message.chat.id,
        product.image,
        caption=caption,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subcategory_"))
async def products(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PaginationState.product)

    _, subcategory = callback.data.split('_')
    await state.update_data(subcategory=subcategory)
    page = 0

    if builder := await get_paginated_builder(state, page):
        await callback.message.edit_text('Выберите товар:', reply_markup=builder.as_markup())
        await state.update_data(page=page)
        await callback.answer()
    else:
        await callback.answer('К сожалению, там пока ничего нет')
        await state.set_state(PaginationState.subcategory)


@router.callback_query(F.data.startswith("category_"))
async def subcategories(callback: CallbackQuery, state: FSMContext) -> None:
    _, category = callback.data.split('_')

    await state.set_state(PaginationState.subcategory)
    await state.update_data(category=category)
    page = 0

    if builder := await get_paginated_builder(state, page):
        await callback.message.edit_text('Выберите подкатегорию:', reply_markup=builder.as_markup())
        await state.update_data(page=page)
        await callback.answer()
    else:
        await callback.answer('К сожалению, там пока ничего нет')
        await state.set_state(PaginationState.category)


@router.callback_query(F.data.startswith("product-cart"))
@inject
async def cart_handler(
    callback: CallbackQuery,
    state: FSMContext,
    repository: AsyncContextManager[Repository] = Provide[Container.repository],
):
    _, action, product_id = callback.data.split("_")
    cart = await Cart().init(state)

    async with repository as repo:
        product = await repo.get_product_by_id(product_id)

    match action:
        case 'add' | 'plus':
            cart.add(product)
            await callback.answer('Товар добавлен в корзину')
        case 'minus':
            cart.decrease(product)
            await callback.answer('Количество товаров уменьшено')
        case 'delete':
            cart.delete(product)
            await callback.answer('Товар удален из корзины')
    await cart.save()

    kb = []

    if product_id in cart:
        kb = get_product_in_cart_nav_keyboard(product_id, cart)
    else:
        kb.append([InlineKeyboardButton(text='Добавить в корзину', callback_data=f'product-cart_add_{product_id}')])
    builder = InlineKeyboardBuilder(kb)

    curr_kb = callback.message.reply_markup.inline_keyboard
    new_kb = builder.as_markup().inline_keyboard

    if not are_keyboards_equal(curr_kb, new_kb):
        await callback.message.edit_reply_markup(callback.inline_message_id, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == 'product-info')
async def product_info_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Текущее значение конкретного товара в корзине')


@router.callback_query(F.data == 'catalog')
async def categories_on_return_button(callback: CallbackQuery, state: FSMContext) -> None:
    page = 0
    await state.update_data(page=page)
    await state.set_state(PaginationState.category)

    builder = await get_paginated_builder(state, page)
    await callback.message.edit_text('Выберите категорию:', reply_markup=builder.as_markup())
    await callback.answer()
