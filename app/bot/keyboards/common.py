from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Payment, Plan


def main_menu(public_site_url: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🚀 Купить VPN", callback_data="plans:list")],
        [InlineKeyboardButton(text="🎁 Тестовый период", callback_data="trial:create")],
        [InlineKeyboardButton(text="👤 Моя подписка", callback_data="subscription:show")],
        [InlineKeyboardButton(text="📲 Инструкции", callback_data="instructions:show")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="support:show")],
        [InlineKeyboardButton(text="🌐 Сайт", url=public_site_url)],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="faq:show")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Админ", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{plan.title} · {plan.price_amount:g} {plan.currency}",
                callback_data=f"plans:select:{plan.id}",
            )
        ]
        for plan in plans
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_details_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", callback_data=f"payments:create:{plan_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="plans:list")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:main")]]
    )


def subscription_keyboard(
    has_subscription_url: bool = False,
    can_add_device: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔄 Обновить статус", callback_data="subscription:show")]]
    if has_subscription_url:
        if can_add_device:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="➕ Добавить устройство",
                        callback_data="subscription:device:add",
                    )
                ]
            )
        rows.append([InlineKeyboardButton(text="📲 Инструкции", callback_data="instructions:show")])
    rows.extend(
        [
            [InlineKeyboardButton(text="⏳ Продлить", callback_data="plans:list")],
            [InlineKeyboardButton(text="Назад", callback_data="menu:main")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [
                InlineKeyboardButton(
                    text="🧾 Ожидают оплаты",
                    callback_data="admin:payments:pending",
                )
            ],
            [InlineKeyboardButton(text="Назад", callback_data="menu:main")],
        ]
    )


def admin_pending_payments_keyboard(payments: list[Payment]) -> InlineKeyboardMarkup:
    rows = []
    for payment in payments:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Подтвердить #{payment.id} · {payment.amount:g} {payment.currency}",
                    callback_data=f"admin:payment:confirm:{payment.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Обновить", callback_data="admin:payments:pending")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)