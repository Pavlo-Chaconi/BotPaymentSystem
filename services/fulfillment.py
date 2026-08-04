import time
import logging
from datetime import datetime, timedelta
from aiogram import Bot

from database.db import (
    get_payment, update_payment_status, add_subscription,
    get_active_subscription, extend_subscription,
)
from services.xui_api import xui_api
from config import SUB_URL

logger = logging.getLogger(__name__)


async def fulfill_payment(payment_id: int, bot: Bot) -> bool:
    """Grants/extends the VPN subscription for a confirmed payment and notifies the user.
    Idempotent: a payment not in 'pending' status is skipped. Returns True on success."""
    payment = await get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        return False

    user_id = payment["user_id"]
    months = payment["months"]

    active_sub = await get_active_subscription(user_id)

    if active_sub:
        email = active_sub["client_email"]
        sub_id = active_sub.get("sub_id")

        current_expires_at = active_sub["expires_at"]
        if current_expires_at and current_expires_at > datetime.now():
            new_expires_at = current_expires_at + timedelta(days=30 * months)
        else:
            new_expires_at = datetime.now() + timedelta(days=30 * months)

        new_expiry_ms = int(new_expires_at.timestamp() * 1000)

        if not await xui_api.update_client_expiry(email, new_expiry_ms):
            logger.error(f"3x-ui update_client_expiry failed for payment {payment_id}")
            return False

        await update_payment_status(payment_id, "successful")
        await extend_subscription(user_id, new_expires_at)

        sub_url = f"{SUB_URL.rstrip('/')}/sub/{sub_id}" if sub_id else "Ссылка-подписка недоступна (старый аккаунт)"
        text = (
            "✅ <b>Оплата подтверждена!</b>\n\n"
            f"Подписка продлена на {months} мес.\n"
            f"Новая дата окончания: {new_expires_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"🔗 <b>Ваша ссылка-подписка (осталась прежней):</b>\n"
            f"<code>{sub_url}</code>"
        )
    else:
        email = f"user_{user_id}_{payment_id}_{int(time.time())}"
        expires_at = datetime.now() + timedelta(days=30 * months)
        expiry_ms = int(expires_at.timestamp() * 1000)

        created = await xui_api.add_client(email=email, expiry_time=expiry_ms)
        if not created:
            logger.error(f"3x-ui add_client failed for payment {payment_id}")
            return False

        client_uuid, new_sub_id = created
        await update_payment_status(payment_id, "successful")
        await add_subscription(user_id, email, client_uuid, new_sub_id, expires_at)

        sub_url = f"{SUB_URL.rstrip('/')}/sub/{new_sub_id}"
        text = (
            "✅ <b>Оплата подтверждена!</b>\n\n"
            f"Подписка на {months} мес. активирована.\n"
            f"Дата окончания: {expires_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"🔗 <b>Ваша ссылка-подписка:</b>\n"
            f"<code>{sub_url}</code>\n\n"
            f"<i>Скопируйте эту ссылку и добавьте в ваше приложение-клиент (v2rayNG, Nekobox и т.д.)</i>"
        )

    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass

    return True
