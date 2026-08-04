import csv
import io
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message

from database.db import import_subscription
from services.xui_api import xui_api
from config import ADMIN_ID

router = Router()

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
    replaced_count = 0

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

            replaced = await import_subscription(telegram_id, email, client_uuid, sub_id, expires_at)
            if replaced:
                replaced_count += 1
            success_count += 1
            # Remove from mapping to track unmapped
            del mapping[email]

    not_found_count = len(mapping)

    report = (
        f"✅ <b>Импорт завершен!</b>\n\n"
        f"Привязано клиентов: <b>{success_count}</b>\n"
        f"Переназначено (была другая активная подписка): <b>{replaced_count}</b>\n"
        f"Не найдено в 3x-ui: <b>{not_found_count}</b>\n\n"
    )
    if not_found_count > 0:
        unmapped_emails = ", ".join(list(mapping.keys())[:10])
        report += f"Некоторые ненайденные: <code>{unmapped_emails}</code>..."

    await msg.edit_text(report, parse_mode="HTML")
