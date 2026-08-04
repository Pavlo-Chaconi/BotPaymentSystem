import logging
from aiohttp import web
from aiogram import Bot

from database.db import get_payment_by_platega_id, update_payment_status
from services.payment_gateway import payment_gateway
from services.fulfillment import fulfill_payment
from config import ADMIN_ID

logger = logging.getLogger(__name__)


def create_webhook_app(bot: Bot) -> web.Application:
    app = web.Application()

    async def platega_webhook(request: web.Request) -> web.Response:
        merchant_id = request.headers.get("X-MerchantId", "")
        secret = request.headers.get("X-Secret", "")
        if not payment_gateway.verify_callback_auth(merchant_id, secret):
            logger.warning("Platega webhook: auth header mismatch")
            return web.Response(status=401)

        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)

        transaction_id = data.get("id")
        status = data.get("status")
        if not transaction_id or not status:
            return web.Response(status=400)

        payment = await get_payment_by_platega_id(transaction_id)
        if not payment:
            logger.warning(f"Platega webhook: unknown transaction {transaction_id}")
            return web.Response(status=404)

        # Idempotent: retries for an already-settled payment are just acknowledged.
        if payment["status"] != "pending":
            return web.Response(status=200)

        if status == "CONFIRMED":
            ok = await fulfill_payment(payment["id"], bot)
            if ok and ADMIN_ID:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"💰 Оплата подтверждена (Platega): payment #{payment['id']}, "
                        f"user {payment['user_id']}, {payment['amount']}₽, {payment['months']} мес."
                    )
                except Exception:
                    pass
            if not ok:
                logger.error(f"Platega webhook: fulfillment failed for payment {payment['id']}")
        elif status == "CANCELED":
            await update_payment_status(payment["id"], "rejected")
            try:
                await bot.send_message(
                    payment["user_id"],
                    "❌ <b>Оплата не прошла.</b>\n\nПопробуйте ещё раз или обратитесь в поддержку.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        return web.Response(status=200)

    app.router.add_post("/platega/webhook", platega_webhook)
    return app
