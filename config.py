import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# 3x-ui settings
XUI_URL = os.getenv("XUI_URL", "https://panel.jewtranstelecom.online/")
XUI_USERNAME = os.getenv("XUI_USERNAME", "JZFpI7mM96")
XUI_PASSWORD = os.getenv("XUI_PASSWORD", "7y9gEiOwMv")

# Domain for subscription links (e.g. https://sub.jewtranstelecom.online/)
SUB_URL = os.getenv("SUB_URL", "https://sub.jewtranstelecom.online/")

# The default inbound ID where clients will be added
XUI_INBOUND_ID = int(os.getenv("XUI_INBOUND_ID", "1"))

# Database settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bot_db")

# Admin settings (for manual payment verification)
# Expecting comma separated string of IDs or a single ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Payment Requisites
PAYMENT_DETAILS = os.getenv("PAYMENT_DETAILS", "Сбербанк / Тинькофф: 0000 0000 0000 0000 (Иван И.)")
