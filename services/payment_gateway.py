import aiohttp
import logging
from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://app.platega.io"

# Set once at startup from bot.get_me() — used to build the return/failedUrl
# deep link Platega redirects the user back to after paying.
BOT_USERNAME = ""


def bot_deeplink() -> str:
    return f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "https://t.me/"


class PlategaGateway:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "X-MerchantId": PLATEGA_MERCHANT_ID,
                "X-Secret": PLATEGA_SECRET_KEY,
                "Content-Type": "application/json",
            })
        return self.session

    async def create_payment(self, amount: int, description: str, payload: str,
                              return_url: str, failed_url: str,
                              user_id: int, username: str):
        """Creates a Platega payment link. Returns {transactionId, url, status, expiresIn} or None."""
        session = await self._get_session()
        body = {
            "paymentDetails": {"amount": amount, "currency": "RUB"},
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
            "payload": payload,
            "metadata": {"userId": str(user_id), "userName": username or str(user_id)},
        }
        try:
            async with session.post(f"{BASE_URL}/v2/transaction/process", json=body) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Platega create_payment -> HTTP {response.status}: {await response.text()}")
                return None
        except aiohttp.ClientError as e:
            logger.error(f"Platega create_payment request failed: {e}")
            return None

    async def get_transaction(self, transaction_id: str):
        """Fetches current status/details of a transaction. Returns dict or None."""
        session = await self._get_session()
        try:
            async with session.get(f"{BASE_URL}/transaction/{transaction_id}") as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"Platega get_transaction -> HTTP {response.status}")
                return None
        except aiohttp.ClientError as e:
            logger.error(f"Platega get_transaction request failed: {e}")
            return None

    @staticmethod
    def verify_callback_auth(merchant_id: str, secret: str) -> bool:
        return merchant_id == PLATEGA_MERCHANT_ID and secret == PLATEGA_SECRET_KEY

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


payment_gateway = PlategaGateway()
