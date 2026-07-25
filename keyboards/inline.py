from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_sub"), InlineKeyboardButton(text="💳 Тарифы", callback_data="buy_sub")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"), InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="📜 Соглашение", callback_data="agreement"), InlineKeyboardButton(text="📄 Документы", callback_data="docs")]
    ])

def buy_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Месяц - 250₽", callback_data="tariff_1_250")],
        [InlineKeyboardButton(text="3 Месяца - 700₽", callback_data="tariff_3_700")],
        [InlineKeyboardButton(text="6 Месяцев - 1350₽", callback_data="tariff_6_1350")],
        [InlineKeyboardButton(text="12 Месяцев - 2500₽", callback_data="tariff_12_2500")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def payment_kb(amount: int, months: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{amount}_{months}")],
        [InlineKeyboardButton(text="Отмена", callback_data="main_menu")]
    ])

def admin_approval_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_approve_{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{payment_id}")
        ]
    ])

def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Документы", callback_data="docs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
