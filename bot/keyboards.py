"""Клавиатуры бота.

ВАЖНО: чтобы Mini App мог вернуть данные боту через Telegram.WebApp.sendData(),
кнопка должна быть кнопкой *reply keyboard* (KeyboardButton + WebAppInfo),
а не inline-кнопкой. Именно поэтому здесь используется ReplyKeyboardMarkup.
"""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

GALLERY_BUTTON_TEXT = "🎨 Открыть галерею промптов"


def gallery_keyboard(webapp_url: str) -> ReplyKeyboardMarkup:
    """Replies-клавиатуру с одной WebApp-кнопкой открытия Mini App.

    one_time_keyboard=False — клавиатура остаётся доступной, чтобы пользователь
    мог открыть галерею повторно после генерации.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=GALLERY_BUTTON_TEXT,
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
