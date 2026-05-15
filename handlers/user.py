import time
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
import qrcode
import io

from database.db import add_user, get_user, get_active_subscription
from keyboards.inline import main_menu_kb, buy_menu_kb, payment_kb, back_to_main_kb
from config import PAYMENT_DETAILS, ADMIN_ID
from utils.states import PaymentStates
from services.xui_api import xui_api

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    welcome_text = (
        "👋 <b>Добро пожаловать в панель управления VPN!</b>\n\n"
        "🛡️ <i>Быстрый, безопасный и анонимный доступ к интернету.</i>\n\n"
        "Выберите действие в меню ниже 👇"
    )
    await message.answer(welcome_text, reply_markup=main_menu_kb(), parse_mode="HTML")

async def navigate_to_text(callback: CallbackQuery, text: str, reply_markup):
    # Утилита для переключения между фото и текстом
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await navigate_to_text(
        callback,
        "🗂 <b>Главное меню:</b>",
        main_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "buy_sub")
async def cb_buy_sub(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await navigate_to_text(
        callback,
        "🛒 <b>Выберите подходящий тарифный план:</b>",
        buy_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff(callback: CallbackQuery, bot: Bot):
    # e.g., tariff_1_100 (1 month, 100 rub)
    _, months, price = callback.data.split("_")
    months = int(months)
    price = int(price)
    
    text = (
        f"📝 <b>Оформление подписки на {months} мес.</b>\n\n"
        f"💳 Сумма к оплате: <b>{price}₽</b>\n\n"
        f"🏦 Реквизиты для перевода:\n"
        f"<code>{PAYMENT_DETAILS}</code>\n\n"
        "<i>После совершения перевода нажмите кнопку «✅ Я оплатил».</i>"
    )
    
    await navigate_to_text(callback, text, payment_kb(price, months))
    await callback.answer()

@router.callback_query(F.data.startswith("paid_"))
async def cb_paid(callback: CallbackQuery, state: FSMContext):
    _, amount, months = callback.data.split("_")
    
    await state.update_data(amount=int(amount), months=int(months))
    await state.set_state(PaymentStates.waiting_for_receipt)
    
    await callback.message.edit_text(
        "📸 Пожалуйста, отправьте фото чека или скриншот перевода ответным сообщением.",
        reply_markup=back_to_main_kb()
    )
    await callback.answer()

@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount")
    months = data.get("months")
    
    photo_file_id = message.photo[-1].file_id
    user_id = message.from_user.id
    
    # We will save this payment in DB in the admin handler when creating the invoice request for admin,
    # or save it here as 'pending' and pass the ID to admin.
    from database.db import create_payment
    payment_id = await create_payment(user_id, amount, months, photo_file_id)
    
    if ADMIN_ID != 0:
        from keyboards.inline import admin_approval_kb
        user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"
        
        admin_text = (
            f"🆕 <b>Новая заявка на оплату!</b>\n\n"
            f"👤 От: {user_info}\n"
            f"💰 Сумма: {amount}₽\n"
            f"📅 Срок: {months} мес.\n\n"
            f"Проверьте чек и примите решение:"
        )
        try:
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo_file_id,
                caption=admin_text,
                reply_markup=admin_approval_kb(payment_id),
                parse_mode="HTML"
            )
        except Exception as e:
            await message.answer("❌ Ошибка при отправке администратору. Свяжитесь с поддержкой.")
            await state.clear()
            return

    await message.answer(
        "✅ Чек успешно отправлен на проверку!\n\n"
        "Обычно проверка занимает от 5 до 15 минут. После проверки вы получите уведомление с ключом доступа.",
        reply_markup=back_to_main_kb()
    )
    await state.clear()

@router.message(PaymentStates.waiting_for_receipt)
async def process_receipt_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте именно ФОТО чека (скриншот).")

@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    sub = await get_active_subscription(user_id)
    
    text = "🪪 <b>Ваш Личный кабинет:</b>\n\n"
    
    if sub:
        email = sub['client_email']
        
        # Сначала получаем актуальные данные из 3x-ui
        traffic = await xui_api.get_client_traffic(email)
        
        if traffic and traffic.get("expiryTime", 0) > 0:
            expires_at_dt = datetime.fromtimestamp(traffic.get("expiryTime") / 1000.0)
            
            # Синхронизируем базу данных с 3x-ui (если админ вручную изменил в панели)
            from database.db import extend_subscription
            await extend_subscription(user_id, expires_at_dt)
            
            expires_at_str = expires_at_dt.strftime("%d.%m.%Y %H:%M")
        else:
            expires_at_dt = sub['expires_at']
            expires_at_str = expires_at_dt.strftime("%d.%m.%Y %H:%M") if isinstance(expires_at_dt, datetime) else expires_at_dt
            
        text += f"🟢 Статус: <b>Активен</b>\n"
        text += f"⏳ Истекает: <b>{expires_at_str}</b>\n\n"
        
        if traffic:
            up = traffic.get("up", 0) / (1024**3) # to GB
            down = traffic.get("down", 0) / (1024**3)
            total = up + down
            text += f"📊 <b>Трафик (VLESS):</b>\n"
            text += f"🌐 Использовано: <b>{total:.2f} GB</b>\n"
        else:
            text += "📊 Статистика трафика пока недоступна.\n"
            
        sub_id = sub.get('sub_id')
        if sub_id:
            from config import SUB_URL
            sub_link = f"{SUB_URL.rstrip('/')}/sub/{sub_id}"
            text += f"\n🔗 Ссылка-подписка сгенерирована в QR-коде.\n"
            text += f"☝️ Вы также можете скопировать её отсюда:\n<code>{sub_link}</code>\n"
            
            # Generate QR
            qr = qrcode.make(sub_link)
            buf = io.BytesIO()
            qr.save(buf, format='PNG')
            buf.seek(0)
            photo = BufferedInputFile(buf.read(), filename="qr.png")
            
            await callback.message.delete()
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=photo,
                caption=text,
                reply_markup=back_to_main_kb(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
    else:
        text += "🔴 Статус: <b>Отсутствует</b>\n"
        text += "<i>Перейдите в меню покупок, чтобы оформить подписку.</i>\n"
    
    await navigate_to_text(callback, text, back_to_main_kb())
    await callback.answer()

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "ℹ️ <b>Инструкция по подключению:</b>\n\n"
        "1️⃣ Скачайте приложение:\n"
        "  • <b>Android:</b> v2rayNG или Nekobox\n"
        "  • <b>iOS:</b> Shadowrocket, V2Box или Streisand\n"
        "  • <b>PC:</b> v2rayN или Nekoray\n\n"
        "2️⃣ Зайдите в «Мой профиль» и скопируйте ссылку-подписку (или отсканируйте QR-код).\n"
        "3️⃣ Вставьте ссылку в ваше приложение (в раздел Подписки / Subscriptions).\n"
        "4️⃣ Обновите подписку и подключитесь!\n\n"
        "💬 Возникли проблемы? Напишите поддержке: @leeengery"
    )
    await navigate_to_text(callback, text, back_to_main_kb())
    await callback.answer()

@router.callback_query(F.data == "agreement")
async def cb_agreement(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "📜 <b>Пользовательское соглашение:</b>\n\n"
        "1. Сервис предоставляет доступ к VPN «как есть».\n"
        "2. Возможны временные перебои в работе, связанные с техническими неполадками, "
        "блокировками со стороны интернет-провайдеров или сбоями магистральных узлов связи.\n"
        "3. Администрация прикладывает все усилия для оперативного восстановления доступа в случае сбоев.\n"
        "4. Оплачивая подписку, вы соглашаетесь с тем, что возврат средств за периоды вынужденного простоя не осуществляется.\n\n"
        "<i>Используя нашего бота, вы подтверждаете согласие с данными условиями.</i>"
    )
    await navigate_to_text(callback, text, back_to_main_kb())
    await callback.answer()
