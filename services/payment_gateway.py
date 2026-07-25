from config import PLATEGA_SHOP_ID, PLATEGA_SECRET_KEY


class PlategaGateway:
    """Placeholder for Platega.io integration."""

    def __init__(self):
        self.shop_id = PLATEGA_SHOP_ID
        self.secret_key = PLATEGA_SECRET_KEY

    async def create_payment(self, amount: int, months: int, user_id: int) -> str:
        # ponytail: stub, no Platega.io docs/creds yet.
        # Wire the real create-invoice call here once available, return the payment URL.
        raise NotImplementedError("Platega.io integration is not wired yet")


platega = PlategaGateway()
