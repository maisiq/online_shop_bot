import logging
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.filters import StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from config import PAYMASTER_TOKEN, bot
from utils import save_order, update_order_on_refund

from .cart import Cart

router = Router()


@router.message(F.text.lower() == 'корзина')
async def cart_handler(
    message: Message,
    state: FSMContext,
) -> None:
    cart = await Cart().init(state)

    builder = InlineKeyboardBuilder()

    if not cart:
        await message.answer("Ваша корзина пуста. Перейдите в каталог для выбора товаров")
        return

    for product_id, product_data in cart:
        builder.button(text=product_data['name'], callback_data=f"product_{product_id}")

    builder.button(text='Редактировать корзину', callback_data="edit_cart")
    builder.button(text='Оформить заказ', callback_data="order_process")

    builder.adjust(1)
    await message.answer(
        "Ваша корзина",
        reply_markup=builder.as_markup()
    )


class CartState(StatesGroup):
    edit = State()


@router.callback_query(or_f(StateFilter(CartState.edit), F.data == 'edit_cart'))
async def cart_edit_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    cart = await Cart().init(state)

    kb = []
    for product_id, product_data in cart:
        kb.append(
            [
                InlineKeyboardButton(text=product_data['name'], callback_data=f'product_{product_id}'),
                InlineKeyboardButton(text='❌ Удалить', callback_data=f'cart-delete_{product_id}'),
            ]
        )
    builder = InlineKeyboardBuilder(kb)
    await callback.message.edit_text('Удалите необходимые товары', reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("cart-delete"))
async def cart_delete_handler(callback: CallbackQuery, state: FSMContext):
    _, product_id = callback.data.split("_")

    cart = await Cart().init(state)
    cart.delete(product_id)
    await cart.save()

    await callback.answer('Товар удален из корзины')

    builder = InlineKeyboardBuilder()

    for product_id, product_data in cart:
        builder.button(text=product_data['name'], callback_data=f'product_{product_id}'),
        builder.button(text='❌ Удалить', callback_data=f'cart-delete_{product_id}')
    builder.adjust(2)

    if cart:
        text = 'Удалите необходимые товары'
    else:
        text = 'Ваша корзина пуста. Перейдите в каталог для выбора товаров'

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


class Order(StatesGroup):
    fio = State()
    phone = State()
    address = State()
    checkout = State()


@router.callback_query(F.data.startswith("order_process"))
async def order_process_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.message.answer('Пожалуйста, введите ФИО получателя полностью')
    await callback.answer()
    await state.set_state(Order.fio)


@router.message(Order.fio)
async def delivery_fio_handler(
    message: Message,
    state: FSMContext,
) -> None:

    await state.update_data(fio=message.text)
    await message.answer(
        f'ФИО получателя: {message.text}\n'
        'Введите номер телефона получателя',
    )
    await state.set_state(Order.phone)


@router.message(Order.phone)
async def delivery_phone_handler(
    message: Message,
    state: FSMContext,
) -> None:

    await state.update_data(phone=message.text)

    await message.answer(
        f'Номер телефона: {message.text}\n'
        'Введите адрес пункта СДЭК',
    )
    await state.set_state(Order.address)


@router.message(Order.address)
async def delivery_address_handler(
    message: Message,
    state: FSMContext,
) -> None:

    await state.update_data(address=message.text)

    data = await state.get_data()

    fio, phone, address = data.get('fio'), data.get('phone'), data.get('address')

    builder = InlineKeyboardBuilder()
    builder.button(text='Paymaster', callback_data="checkout-invoice_paymaster")

    cart = await Cart().init(state)
    text = await get_order_reperesentation(cart)
    delivery_details = (
        f'ФИО получателя: {fio}\n'
        f'Номер телефона: {phone}\n'
        f'Пункт выдачи: {address}\n\n'
        'Выберите способ оплаты:'
    )
    await message.answer(
        text + delivery_details,
        reply_markup=builder.as_markup(),
    )

    await state.set_state(Order.checkout)


async def get_order_reperesentation(cart: Cart):
    total_price = cart.total()
    order_list = [f'{pd['name']} ✕ {pd['quantity']} шт.' for _, pd in cart]

    text = '\n'.join(order_list) + f'\n\nСумма к оплате: {total_price}\n\n'
    return text


@router.callback_query(F.data.startswith("checkout-invoice"))
async def process_buy_handler(callback: CallbackQuery, state: FSMContext):

    pay_option = callback.data.split('_')[1]
    cart = await Cart().init(state)

    prices = [
        types.LabeledPrice(
            label=product['name'],
            amount=str(Decimal(product['price']) * product['quantity'] * 100)
        )
        for _, product in cart
    ]
    desc = 'Для оплаты нажмите на кнопку ниже'

    match pay_option:
        case 'paymaster':
            token = PAYMASTER_TOKEN

    await callback.answer()

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Оплата заказа",
        description=desc,
        provider_token=token,
        currency="RUB",
        prices=prices,
        payload="premium-subscription-1",
        start_parameter="premium",
        is_flexible=False,
    )


# Для использования оформления доставки внутри телеграма

@router.shipping_query()
async def handle_shipping_query(shipping_query: types.ShippingQuery):
    if shipping_query.shipping_address.country_code == "RU":
        shipping_options = [
            types.ShippingOption(
                id="post",
                title="Почта России",
                prices=[types.LabeledPrice(label="Доставка", amount=50000)]
            ),
            types.ShippingOption(
                id="cdek",
                title="СДЭК",
                prices=[types.LabeledPrice(label="Доставка", amount=55000)]
            )
        ]
        await shipping_query.answer(
            ok=True,
            shipping_options=shipping_options
        )
    else:
        await shipping_query.answer(
            ok=False,
            error_message="Извините, доставка в вашу страну недоступна."
        )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    # *Проверка*
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(lambda message: message.successful_payment is not None)
async def process_payment(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    cart = await Cart().init(state)
    payment = message.successful_payment

    # Сохраняем заказ в excel таблицу
    save_order(
        client_username=message.from_user.username,
        products=list(cart),
        provider_payment_charge_id=payment.provider_payment_charge_id,
        paid_amount=payment.total_amount / 100,
        fio=user_data.get('fio'),
        phone=user_data.get('phone'),
        address=user_data.get('address'),
    )
    logging.info('Новый заказ от %s', message.from_user.username)

    await message.answer("✅ Платеж успешно завершен! Спасибо!")


@router.message(lambda message: message.refunded_payment is not None)
async def process_refunded_payment(message: types.Message):
    refund = message.refunded_payment

    # При возврате средств изменяем статус заказа
    update_order_on_refund(refund.provider_payment_charge_id)
    logging.info('Возврат средств от %s', message.from_user.username)

    await message.answer(
        f"Возврат платежа на сумму {refund.total_amount / 100} {refund.currency}"
    )
