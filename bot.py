import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.db import init_db, close_db
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from services.xui_api import xui_api

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
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await xui_api.close()
        await close_db()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
