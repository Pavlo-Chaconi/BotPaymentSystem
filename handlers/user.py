import os
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
import qrcode
import io

from database.db import (
    add_user, get_active_subscription, create_gateway_payment, get_payment_by_platega_id,
    update_payment_status, get_subscription_by_client_uuid, import_subscription,
)
from keyboards.inline import main_menu_kb, buy_menu_kb, gateway_payment_kb, back_to_main_kb, agreement_kb, no_subscription_kb
from config import SUPPORT_EMAIL, ADMIN_ID
from services.xui_api import xui_api
from services.payment_gateway import payment_gateway, bot_deeplink
from services.fulfillment import fulfill_payment
from utils.states import RestoreStates

router = Router()

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
PRIVACY_POLICY_PATH = os.path.join(DOCS_DIR, "privacy_policy.pdf")
TERMS_OF_SERVICE_PATH = os.path.join(DOCS_DIR, "terms_of_service.pdf")

async def send_docs(chat_id: int, bot: Bot):
    if os.path.exists(PRIVACY_POLICY_PATH):
        await bot.send_document(chat_id, FSInputFile(PRIVACY_POLICY_PATH), caption="🔒 Политика конфиденциальности")
    if os.path.exists(TERMS_OF_SERVICE_PATH):
        await bot.send_document(chat_id, FSInputFile(TERMS_OF_SERVICE_PATH), caption="📄 Пользовательское соглашение")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    is_new = await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if is_new:
        await send_docs(message.chat.id, bot)
        welcome_text = (
            "👋 <b>Добро пожаловать в панель управления VPN!</b>\n\n"
            "🛡️ <i>Быстрый, безопасный и анонимный доступ к интернету.</i>\n\n"
            "Ознакомьтесь с документами выше перед началом работы.\n"
            "Выберите действие в меню ниже 👇"
        )
    else:
        welcome_text = (
            "👋 <b>С возвращением!</b>\n\n"
            "🛡️ <i>Быстрый, безопасный и анонимный доступ к интернету.</i>\n\n"
            "Выберите действие в меню ниже 👇"
        )
    await message.answer(welcome_text, reply_markup=main_menu_kb(), parse_mode="HTML")

@router.callback_query(F.data == "docs")
async def cb_docs(callback: CallbackQuery, bot: Bot):
    await send_docs(callback.message.chat.id, bot)
    await callback.answer()

@router.callback_query(F.data == "support")
async def cb_support(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = f"🆘 <b>Поддержка</b>\n\nПо всем вопросам пишите: {SUPPORT_EMAIL}"
    await navigate_to_text(callback, text, back_to_main_kb())
    await callback.answer()

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
    # e.g., tariff_1_250 (1 month, 250 rub)
    _, months, price = callback.data.split("_")
    months = int(months)
    price = int(price)
    user_id = callback.from_user.id

    deeplink = bot_deeplink()
    created = await payment_gateway.create_payment(
        amount=price,
        description=f"VPN подписка на {months} мес.",
        payload=f"tg:{user_id}",
        return_url=deeplink,
        failed_url=deeplink,
        user_id=user_id,
        username=callback.from_user.username,
    )

    if not created or not created.get("url") or not created.get("transactionId"):
        text = (
            "❌ <b>Не удалось создать платёж.</b>\n\n"
            f"Попробуйте ещё раз чуть позже или свяжитесь с поддержкой ({SUPPORT_EMAIL})."
        )
        await navigate_to_text(callback, text, back_to_main_kb())
        await callback.answer()
        return

    await create_gateway_payment(user_id, price, months, created["transactionId"])

    text = (
        f"📝 <b>Оформление подписки на {months} мес.</b>\n\n"
        f"💳 Сумма к оплате: <b>{price}₽</b>\n\n"
        "Нажмите «Оплатить», выберите удобный способ оплаты на странице Platega — "
        "подписка активируется автоматически сразу после оплаты."
    )
    await navigate_to_text(callback, text, gateway_payment_kb(created["url"], created["transactionId"]))
    await callback.answer()

@router.callback_query(F.data.startswith("check_"))
async def cb_check_payment(callback: CallbackQuery, bot: Bot):
    transaction_id = callback.data[len("check_"):]
    payment = await get_payment_by_platega_id(transaction_id)

    if not payment:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    if payment["status"] != "pending":
        await callback.answer("Этот платёж уже обработан.", show_alert=True)
        return

    remote = await payment_gateway.get_transaction(transaction_id)
    status = remote.get("status") if remote else None

    if status == "CONFIRMED":
        if await fulfill_payment(payment["id"], bot):
            await callback.message.edit_text(
                "✅ Оплата подтверждена! Подписка активирована — подробности отправлены отдельным сообщением.",
                reply_markup=back_to_main_kb()
            )
        else:
            await callback.answer("Оплата подтверждена, но выдача не удалась. Свяжитесь с поддержкой.", show_alert=True)
    elif status == "CANCELED":
        await update_payment_status(payment["id"], "rejected")
        await callback.answer("Платёж отменён.", show_alert=True)
    else:
        await callback.answer("Платёж пока не оплачен.", show_alert=True)

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
        text += "<i>Оформите новую подписку или восстановите уже купленную по ссылке.</i>\n"
        await navigate_to_text(callback, text, no_subscription_kb())
        await callback.answer()
        return

    await navigate_to_text(callback, text, back_to_main_kb())
    await callback.answer()

@router.callback_query(F.data == "restore_sub")
async def cb_restore_sub(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RestoreStates.waiting_for_key)
    await navigate_to_text(
        callback,
        "🔄 <b>Восстановление подписки</b>\n\n"
        "Пришлите ссылку-подписку (или её код) следующим сообщением — я найду её и привяжу к вашему аккаунту.",
        back_to_main_kb()
    )
    await callback.answer()

@router.message(RestoreStates.waiting_for_key, F.text)
async def process_restore_key(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = message.from_user.id

    token = message.text.strip().rstrip("/").split("/")[-1].split("?")[0]
    client = await xui_api.find_client(token)

    if not client:
        await message.answer(
            "❌ Не нашёл подписку по этой ссылке/коду. Проверьте и попробуйте ещё раз, "
            f"либо напишите в поддержку ({SUPPORT_EMAIL}).",
            reply_markup=back_to_main_kb()
        )
        return

    client_uuid = client["uuid"]
    existing = await get_subscription_by_client_uuid(client_uuid)

    if existing and existing["user_id"] != user_id:
        await message.answer(
            "❌ Эта подписка уже привязана к другому аккаунту. "
            f"Если это ошибка — напишите в поддержку ({SUPPORT_EMAIL}).",
            reply_markup=back_to_main_kb()
        )
        return

    if existing and existing["user_id"] == user_id and existing["status"] == "active":
        await message.answer("ℹ️ Эта подписка уже привязана к вашему аккаунту.", reply_markup=back_to_main_kb())
        return

    expiry_ms = client.get("expiryTime", 0)
    expires_at = datetime.fromtimestamp(expiry_ms / 1000.0) if expiry_ms > 0 else datetime.now() + timedelta(days=3650)

    await import_subscription(user_id, client["email"], client_uuid, client.get("subId", ""), expires_at)

    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🔄 Восстановлена подписка: user {user_id} <-> {client['email']}")
        except Exception:
            pass

    await message.answer(
        "✅ <b>Подписка восстановлена и привязана к вашему аккаунту!</b>\n\n"
        f"Дата окончания: <b>{expires_at.strftime('%d.%m.%Y %H:%M')}</b>\n\n"
        "Подробности — в разделе «👤 Мой профиль».",
        reply_markup=back_to_main_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "locations")
async def cb_locations(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    locations = await xui_api.get_locations()

    text = "🌍 <b>Доступные локации:</b>\n\n"
    if locations:
        for loc in locations:
            icon = "🟢" if loc["online"] else "🔴"
            text += f"{icon} {loc['label']}\n"
    else:
        text += "<i>Не удалось получить список локаций. Попробуйте позже.</i>\n"

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
        f"💬 Возникли проблемы? Напишите поддержке: {SUPPORT_EMAIL}"
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
    await navigate_to_text(callback, text, agreement_kb())
    await callback.answer()
