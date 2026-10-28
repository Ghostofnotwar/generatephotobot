"""aiogram-хэндлеры бота."""

from __future__ import annotations

import json
import logging

from aiogram import Router, types
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.types import BufferedInputFile

from .config import Settings
from .keyboards import gallery_keyboard
from .services import (
    CloudflareAPIError,
    ImageGenerationError,
    RateLimitError,
    generate_image_flux,
)

logger = logging.getLogger(__name__)

START_TEXT = (
    "🎨 <b>Photo Generator Bot</b>\n\n"
    "Откройте галерею превью, выберите тему — и сгенерируйте уникальное "
    "изображение через Cloudflare Workers AI (FLUX.1 Schnell).\n\n"
    "Нажмите кнопку ниже, чтобы открыть Mini App."
)

HELP_TEXT = (
    "<b>Как это работает</b>\n\n"
    "1. Нажмите «Открыть галерею промптов».\n"
    "2. Выберите карточку темы — промпт подставится автоматически.\n"
    "3. При необходимости отредактируйте промпт и переключите язык.\n"
    "4. Нажмите «Сгенерировать» — бот отправит готовое изображение.\n\n"
    "<i>Изображения генерируются моделью @cf/black-forest-labs/flux-1-schnell.</i>"
)

_LANG_NAMES = {"ru": "Русский", "en": "English"}


class WebAppDataFilter(BaseFilter):
    """Фильтр: сообщения-сервисные от Mini App (sendData)."""

    async def __call__(self, message: types.Message) -> bool:
        return message.web_app_data is not None


def _escape(text: str) -> str:
    """Экранировать спецсимволы HTML для parse_mode=HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_caption(payload: dict, prompt: str, lang: str, limit: int = 980) -> str:
    lines: list[str] = []
    theme_title = payload.get("theme_title")
    if theme_title:
        lines.append(f"🎨 <b>{_escape(str(theme_title))}</b>")
    shown = prompt if len(prompt) <= 300 else prompt[:297] + "..."
    lines.append(f"<b>Промпт:</b> {_escape(shown)}")
    lines.append(f"<b>Язык:</b> {_LANG_NAMES.get(lang, lang)}")
    lines.append("<i>FLUX.1 Schnell · Cloudflare Workers AI</i>")
    caption = "\n".join(lines)
    if len(caption) > limit:
        caption = caption[:limit] + "\n…"
    return caption


def build_router(settings: Settings) -> Router:
    """Собрать Router с хэндлерами, привязанными к settings через замыкание."""
    router = Router()
    keyboard = gallery_keyboard(settings.webapp_url)

    @router.message(CommandStart())
    async def cmd_start(message: types.Message) -> None:
        await message.answer(START_TEXT, reply_markup=keyboard)

    @router.message(Command("help"))
    async def cmd_help(message: types.Message) -> None:
        await message.answer(HELP_TEXT, reply_markup=keyboard)

    @router.message(WebAppDataFilter())
    async def handle_web_app_data(message: types.Message) -> None:
        await _handle_generate(message, settings, keyboard)

    return router


async def _handle_generate(
    message: types.Message, settings: Settings, keyboard: types.ReplyKeyboardMarkup
) -> None:
    user = message.from_user
    if settings.allowed_user_id is not None:
        if user is None or user.id != settings.allowed_user_id:
            await message.answer("⛔ Этот бот доступен только авторизованным пользователям.")
            return

    raw = message.web_app_data.data if message.web_app_data else ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await message.answer("⚠️ Получены некорректные данные от Mini App.")
        return

    if not isinstance(payload, dict) or payload.get("action") != "generate":
        await message.answer("⚠️ Неподдерживаемое действие от Mini App.")
        return

    prompt = str(payload.get("prompt", "")).strip()
    lang = str(payload.get("lang", "ru")).lower()

    if not prompt:
        await message.answer("⚠️ Промпт пуст. Выберите тему в галерее и попробуйте снова.")
        return
    if len(prompt) > settings.max_prompt_chars:
        await message.answer(
            f"⚠️ Промпт слишком длинный ({len(prompt)} знаков). "
            f"Максимум — {settings.max_prompt_chars}."
        )
        return

    await message.answer("⏳ Генерирую изображение…")

    try:
        image_bytes, mime = await generate_image_flux(prompt, settings)
    except RateLimitError as exc:
        logger.warning("Rate limit for user %s: %s", user.id if user else "?", exc)
        await message.answer("⏳ Лимит запросов Cloudflare истек. Подождите минуту и попробуйте снова.")
        return
    except CloudflareAPIError as exc:
        logger.error("Cloudflare API error: %s", exc)
        await message.answer(f"⚠️ Ошибка Cloudflare: {exc}")
        return
    except ImageGenerationError as exc:
        logger.exception("Image generation failed: %s", exc)
        await message.answer("⚠️ Не удалось сгенерировать изображение. Проверьте настройки Cloudflare.")
        return

    caption = _build_caption(payload, prompt, lang)

    photo = BufferedInputFile(file=image_bytes, filename="generated_image.jpg")
    await message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
