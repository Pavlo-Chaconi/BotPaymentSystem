from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="buy_sub")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🌍 Локации", callback_data="locations")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"), InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="📜 Соглашение", callback_data="agreement")]
    ])

def buy_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Месяц - 250₽", callback_data="tariff_1_250")],
        [InlineKeyboardButton(text="3 Месяца - 700₽", callback_data="tariff_3_700")],
        [InlineKeyboardButton(text="6 Месяцев - 1350₽", callback_data="tariff_6_1350")],
        [InlineKeyboardButton(text="12 Месяцев - 2500₽", callback_data="tariff_12_2500")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def gateway_payment_kb(pay_url: str, transaction_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_{transaction_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def no_subscription_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="buy_sub")],
        [InlineKeyboardButton(text="🔄 Восстановить подписку", callback_data="restore_sub")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def agreement_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Документы", callback_data="docs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
