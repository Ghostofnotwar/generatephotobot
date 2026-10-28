"""Сервисы бота: работа с промптами и интеграция с Cloudflare Workers AI.

Модель: @cf/black-forest-labs/flux-1-schnell
REST-эндпоинт:
    POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell

Успешный ответ (Content-Type: application/json):
    { "result": { "image": "<base64-строка>" }, "errors": [], "messages": [] }
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl

import aiohttp

from .config import Settings

logger = logging.getLogger(__name__)

FLUX_MODEL = "@cf/black-forest-labs/flux-1-schnell"
FLUX_ENDPOINT = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
    + FLUX_MODEL
)

# Потенциально критичные коды ошибок Cloudflare для FLUX-моделей.
_RATE_LIMIT_CODES = {7000, 7003}


# --------------------------------------------------------------------------- #
# Ошибки
# --------------------------------------------------------------------------- #
class PromptError(Exception):
    """Не удалось прочитать/разобрать файл промптов."""


class ImageGenerationError(Exception):
    """Базовая ошибка генерации изображения."""


class RateLimitError(ImageGenerationError):
    """Лимит запросов Cloudflare Workers AI истек."""


class CloudflareAPIError(ImageGenerationError):
    """Cloudflare вернула неуспешный ответ."""


# --------------------------------------------------------------------------- #
# Промпты
# --------------------------------------------------------------------------- #
def load_prompts(path: str | Path) -> list[dict]:
    """Загрузить список промптов из JSON.

    Поддерживает два формата:
      1) Список объектов:  [ {...}, {...} ]
      2) Объект с ключом prompts/items/data/gallery:  { "prompts": [...] }

    Each item нормализуется в словарь с ключами:
      id, theme, title_ru, title_en, prompt_ru, prompt_en, preview_url,
      tags, steps, seed
    """

    p = Path(path)
    if not p.exists():
        raise PromptError(f"Файл промптов не найден: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromptError(f"Некорректный JSON в файле промптов {p}: {exc}") from exc

    if isinstance(raw, dict):
        for key in ("prompts", "items", "data", "gallery"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = [raw]

    if not isinstance(raw, list):
        raise PromptError("Файл промптов должен содержать массив объектов.")

    prompts: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise PromptError(f"Промпт №{i} должен быть объектом.")
        prompts.append(
            {
                "id": item.get("id", i + 1),
                "theme": str(item.get("theme") or f"theme-{i + 1}").strip(),
                "title_ru": str(item.get("title_ru") or item.get("theme") or f"Тема {i + 1}"),
                "title_en": str(item.get("title_en") or item.get("theme") or f"Theme {i + 1}"),
                "prompt_ru": str(item.get("prompt_ru") or item.get("prompt") or ""),
                "prompt_en": str(item.get("prompt_en") or item.get("prompt_ru") or item.get("prompt") or ""),
                "preview_url": str(item.get("preview_url") or ""),
                "tags": [str(t) for t in (item.get("tags") or [])],
                "steps": item.get("steps"),
                "seed": item.get("seed"),
            }
        )
    return prompts


# --------------------------------------------------------------------------- #
# Cloudflare Workers AI
# --------------------------------------------------------------------------- #
def _decode_image_response(body: bytes, content_type: str | None) -> bytes:
    """Разобрать ответ Workers AI и вернуть сырые биты изображения."""
    if (content_type or "").lower().startswith("image/"):
        # Некоторые модели/режимы возвращают уже готовое изображение.
        return body

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CloudflareAPIError("Некорректный ответ Cloudflare: ожидался JSON.") from exc

    result = data.get("result")
    if not isinstance(result, dict):
        errors = data.get("errors") or []
        detail = ""
        if errors and isinstance(errors[0], dict):
            detail = str(errors[0].get("message") or "")
        raise CloudflareAPIError(
            "Cloudflare не вернул изображение." + (f" {detail}" if detail else "")
        )

    image_b64 = result.get("image")
    if not image_b64:
        raise CloudflareAPIError("Cloudflare вернул пустое изображение (поле image).")

    try:
        return base64.b64decode(image_b64)
    except (binascii.Error, ValueError) as exc:
        raise CloudflareAPIError("Не удалось декодировать Base64-изображение.") from exc


def _error_from_response(status: int, body: bytes) -> ImageGenerationError:
    """Построить информативную ошибку из неуспешного ответа Cloudflare."""
    detail = ""
    code: int | None = None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {}
    errors = data.get("errors") or []
    if errors and isinstance(errors[0], dict):
        code = errors[0].get("code")
        detail = str(errors[0].get("message") or "")

    if status == 429 or code in _RATE_LIMIT_CODES or "rate" in (detail or "").lower():
        return RateLimitError(
            "Лимит запросов Cloudflare Workers AI истек. Подождите минуту и попробуйте снова."
        )

    parts = [f"Cloudflare API вернул ошибку {status}."]
    if code is not None:
        parts.append(f"Код: {code}.")
    if detail:
        parts.append(detail)
    if status in (401, 403):
        parts.append("Проверьте CLOUDFLARE_API_TOKEN и права на Workers AI.")
    if status >= 500:
        parts.append("Временно недоступен — попробуйте позже.")
    return CloudflareAPIError(" ".join(parts))


async def generate_image_flux(prompt: str, settings: Settings) -> tuple[bytes, str]:
    """Сгенерировать изображение через Cloudflare Workers AI (FLUX.1 Schnell).

    Возвращает (image_bytes, mime_type).
    Raises RateLimitError / CloudflareAPIError / ImageGenerationError.
    """
    url = FLUX_ENDPOINT.format(account_id=settings.cloudflare_account_id)
    headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
    payload: dict = {"prompt": prompt, "steps": settings.flux_steps}

    timeout = aiohttp.ClientTimeout(total=settings.http_timeout)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                body = await resp.read()
                if resp.status == 200:
                    return _decode_image_response(body, resp.content_type), "image/jpeg"
                raise _error_from_response(resp.status, body)
    except aiohttp.ClientError as exc:
        raise ImageGenerationError(f"Не удалось достичь API Cloudflare: {exc}") from exc


# --------------------------------------------------------------------------- #
# Валидация initData Telegram (для прямого HTTP API)
# --------------------------------------------------------------------------- #
def verify_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = 300
) -> tuple[bool, dict]:
    """Проверить подпись initData Mini App (HMAC-SHA256).

    Возвращает (ok, parsed_fields). Используется для защиты прямого HTTP API.
    """
    if not init_data:
        return False, {}
    try:
        fields = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return False, {}

    received_hash = fields.pop("hash", "")
    auth_date_raw = fields.get("auth_date")
    try:
        auth_date = int(auth_date_raw) if auth_date_raw else 0
    except (TypeError, ValueError):
        return False, fields

    if not auth_date or abs(time.time() - auth_date) > max_age_seconds:
        return False, fields

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, received_hash), fields
