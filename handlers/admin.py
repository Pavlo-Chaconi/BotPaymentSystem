import time
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from database.db import get_payment, update_payment_status, add_subscription, get_active_subscription, extend_subscription
from services.xui_api import xui_api
from config import ADMIN_ID, SUB_URL

router = Router()

@router.callback_query(F.data.startswith("admin_approve_"))
async def cb_admin_approve(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
        
    payment_id = int(callback.data.split("_")[2])
    payment = await get_payment(payment_id)
    
    if not payment:
        await callback.answer("Платеж не найден.", show_alert=True)
        return
        
    if payment['status'] != 'pending':
        await callback.answer(f"Платеж уже обработан (Статус: {payment['status']}).", show_alert=True)
        return

    user_id = payment['user_id']
    months = payment['months']
    
    if months <= 0:
        await callback.message.answer("❌ Ошибка: неверное количество месяцев.")
        await callback.answer()
        return

    # Check if user already has an active subscription
    active_sub = await get_active_subscription(user_id)
    
    if active_sub:
        # Extend existing
        email = active_sub['client_email']
        sub_id = active_sub.get('sub_id')

        current_expires_at = active_sub['expires_at']
        if current_expires_at and current_expires_at > datetime.now():
            new_expires_at = current_expires_at + timedelta(days=30 * months)
        else:
            new_expires_at = datetime.now() + timedelta(days=30 * months)

        new_expiry_ms = int(new_expires_at.timestamp() * 1000)

        success = await xui_api.update_client_expiry(email, new_expiry_ms)
        if success:
            await update_payment_status(payment_id, "successful")
            await extend_subscription(user_id, new_expires_at)
            
            sub_url = f"{SUB_URL.rstrip('/')}/sub/{sub_id}" if sub_id else "Ссылка-подписка недоступна (старый аккаунт)"
            
            success_text = (
                "✅ <b>Ваш платеж подтвержден!</b>\n\n"
                f"Текущая подписка успешно продлена на {months} мес.\n"
                f"Новая дата окончания: {new_expires_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"🔗 <b>Ваша ссылка-подписка (осталась прежней):</b>\n"
                f"<code>{sub_url}</code>"
            )
            try:
                await bot.send_message(user_id, success_text, parse_mode="HTML")
            except:
                pass
                
            await callback.message.edit_caption(
                caption=callback.message.caption + f"\n\n✅ ОДОБРЕНО. Продлено до {new_expires_at.strftime('%Y-%m-%d')}.",
                reply_markup=None
            )
        else:
            await callback.message.answer("❌ Ошибка при продлении в 3x-ui!")
    else:
        # Create new
        email = f"user_{user_id}_{payment_id}_{int(time.time())}"
        expires_at = datetime.now() + timedelta(days=30 * months)
        expiry_ms = int(expires_at.timestamp() * 1000)

        created = await xui_api.add_client(email=email, expiry_time=expiry_ms)

        if created:
            client_uuid, new_sub_id = created
            await update_payment_status(payment_id, "successful")
            await add_subscription(user_id, email, client_uuid, new_sub_id, expires_at)

            sub_url = f"{SUB_URL.rstrip('/')}/sub/{new_sub_id}"
            
            success_text = (
                "✅ <b>Ваш платеж подтвержден!</b>\n\n"
                f"Подписка на {months} мес. активирована.\n"
                f"Дата окончания: {expires_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"🔗 <b>Ваша ссылка-подписка:</b>\n"
                f"<code>{sub_url}</code>\n\n"
                f"<i>Скопируйте эту ссылку и добавьте в ваше приложение-клиент (v2rayNG, Nekobox и т.д.)</i>"
            )
            try:
                await bot.send_message(user_id, success_text, parse_mode="HTML")
            except:
                pass
                
            await callback.message.edit_caption(
                caption=callback.message.caption + f"\n\n✅ ОДОБРЕНО И ВЫДАНО.",
                reply_markup=None
            )
        else:
            await callback.message.answer("❌ Ошибка выдачи в 3x-ui! Платеж не отмечен как успешный.")
            
    await callback.answer()

import csv
import io
from aiogram.types import Message
from database.db import import_subscription

@router.message(F.document, F.caption == "/import")
async def handle_import_csv(message: Message, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.document.file_name.endswith('.csv'):
        await message.answer("❌ Пожалуйста, отправьте файл в формате .csv")
        return

    msg = await message.answer("⏳ Загрузка и анализ файла...")

    # Download file into memory
    file_in_memory = io.BytesIO()
    await bot.download(message.document, destination=file_in_memory)
    file_in_memory.seek(0)
    
    # Read CSV
    raw_data = file_in_memory.read()
    text_data = None
    for enc in ['utf-8-sig', 'cp1251', 'utf-16', 'latin-1']:
        try:
            text_data = raw_data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
            
    if text_data is None:
        text_data = raw_data.decode('utf-8', errors='replace')
        
    mapping = {}
    for line in text_data.splitlines():
        if not line.strip():
            continue
        # Normalize delimiters: Excel in Russian often uses ';' instead of ','
        normalized_line = line.replace(';', ',')
        parts = [p.strip() for p in normalized_line.split(',')]
        
        if len(parts) >= 2:
            email = parts[0]
            try:
                tg_id = int(parts[1])
                mapping[email] = tg_id
            except ValueError:
                continue

    if not mapping:
        await msg.edit_text("❌ В файле не найдено корректных данных. Формат: email,telegram_id")
        return

    await msg.edit_text("⏳ Получение клиентов из 3x-ui...")
    xui_clients = await xui_api.list_clients()

    if not xui_clients:
        await msg.edit_text("❌ В 3x-ui не найдено клиентов.")
        return

    success_count = 0
    not_found_count = 0

    for client in xui_clients:
        email = client.get("email")
        if email in mapping:
            client_uuid = client.get("uuid")
            sub_id = client.get("subId", "")
            expiry_ms = client.get("expiryTime", 0)
            
            # calculate expires_at
            if expiry_ms > 0:
                # assuming expiry_ms is timestamp in milliseconds
                expires_at = datetime.fromtimestamp(expiry_ms / 1000.0)
            else:
                # unlimited time - set some far future date
                expires_at = datetime.now() + timedelta(days=3650)
                
            telegram_id = mapping[email]
            
            await import_subscription(telegram_id, email, client_uuid, sub_id, expires_at)
            success_count += 1
            # Remove from mapping to track unmapped
            del mapping[email]
            
    not_found_count = len(mapping)
    
    report = (
        f"✅ <b>Импорт завершен!</b>\n\n"
        f"Привязано клиентов: <b>{success_count}</b>\n"
        f"Не найдено в 3x-ui: <b>{not_found_count}</b>\n\n"
    )
    if not_found_count > 0:
        unmapped_emails = ", ".join(list(mapping.keys())[:10])
        report += f"Некоторые ненайденные: <code>{unmapped_emails}</code>..."

    await msg.edit_text(report, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_reject_"))
async def cb_admin_reject(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
        
    payment_id = int(callback.data.split("_")[2])
    payment = await get_payment(payment_id)
    
    if not payment:
        await callback.answer("Платеж не найден.", show_alert=True)
        return
        
    if payment['status'] != 'pending':
        await callback.answer(f"Платеж уже обработан (Статус: {payment['status']}).", show_alert=True)
        return
        
    await update_payment_status(payment_id, "rejected")
    
    reject_text = (
        "❌ <b>Оплата не подтверждена.</b>\n\n"
        "Мы не смогли найти ваш платеж или скриншот недействителен.\n"
        "Пожалуйста, свяжитесь с поддержкой для уточнения деталей."
    )
    
    try:
        await bot.send_message(payment['user_id'], reject_text, parse_mode="HTML")
    except:
        pass

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ ОТКЛОНЕНО.",
        reply_markup=None
    )
    await callback.answer()
