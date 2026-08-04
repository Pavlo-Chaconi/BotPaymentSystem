import logging
from aiogram import Bot

from database.db import get_subscriptions_expiring_soon, mark_reminder_sent

logger = logging.getLogger(__name__)

EXPIRY_WARNING_DAYS = 7


async def check_expiring_subscriptions(bot: Bot):
    subs = await get_subscriptions_expiring_soon(EXPIRY_WARNING_DAYS)
    for sub in subs:
        text = (
            "⏰ <b>Ваша подписка скоро истекает!</b>\n\n"
            f"Дата окончания: <b>{sub['expires_at'].strftime('%d.%m.%Y %H:%M')}</b>\n\n"
            "Продлите подписку заранее, чтобы не потерять доступ — в разделе «💳 Тарифы»."
        )
        try:
            await bot.send_message(sub["user_id"], text, parse_mode="HTML")
            await mark_reminder_sent(sub["id"])
        except Exception as e:
            logger.warning(f"Failed to send expiry reminder to {sub['user_id']}: {e}")
