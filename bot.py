import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, WEBHOOK_PORT
from database.db import init_db, close_db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from handlers.webhook import create_webhook_app
from services.xui_api import xui_api
from services.payment_gateway import payment_gateway
import services.payment_gateway as payment_gateway_module

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting bot...")

    # Initialize Database
    await init_db()

    # Sanity-check 3x-ui connectivity/token
    if await xui_api.list_clients():
        logger.info("3x-ui API reachable")
    else:
        logger.warning("3x-ui API unreachable or returned no clients. Check XUI_URL/XUI_API_TOKEN.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(user_router)
    dp.include_router(admin_router)

    me = await bot.get_me()
    payment_gateway_module.BOT_USERNAME = me.username

    webhook_app = create_webhook_app(bot)
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBHOOK_PORT)
    await site.start()
    logger.info(f"Platega webhook listening on :{WEBHOOK_PORT}/platega/webhook")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await payment_gateway.close()
        await xui_api.close()
        await close_db()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
