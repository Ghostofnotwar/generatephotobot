"""Опциональный прямой HTTP API бота.

Включается настройкой BOT_API_HOST. Позволяет Mini App отправлять промпт
напрямую на бэкенд (POST /generate) вместо Telegram.WebApp.sendData — это
нужно для промптов длиннее 4096 байт или если мини-приложение открыто не
из reply-клавиатуры (где sendData недоступен).

Трафик подтверждается via X-Telegram-Init-Data (HMAC-проверка, см. services).
"""

from __future__ import annotations

import base64
import json
import logging

from aiohttp import web

from .config import Settings
from .services import (
    ImageGenerationError,
    PromptError,
    RateLimitError,
    generate_image_flux,
    load_prompts,
    verify_init_data,
)

logger = logging.getLogger(__name__)


def _cors_middleware(allowed_origin: str | None):
    @web.middleware
    async def middleware(request: web.Request, handler) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
        else:
            try:
                resp = await handler(request)
            except web.HTTPException as exc:
                resp = exc
        if allowed_origin and origin == allowed_origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-Telegram-Init-Data"
            )
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp

    return middleware


def create_app(settings: Settings) -> web.Application:
    app = web.Application(middlewares=[_cors_middleware(settings.http_cors_origin)])
    app["settings"] = settings

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def prompts(request: web.Request) -> web.Response:
        try:
            items = load_prompts(settings.prompts_path)
        except PromptError as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"prompts": items})

    async def generate(request: web.Request) -> web.Response:
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        ok, user_data = verify_init_data(init_data, settings.bot_token)
        if not ok:
            return web.json_response(
                {"error": "Невалидные или устаревшие данные initData."}, status=403
            )

        if settings.allowed_user_id is not None:
            try:
                tg_id = int(user_data.get("id"))
            except (TypeError, ValueError):
                return web.json_response({"error": "Не удалось определить пользователя."}, status=403)
            if tg_id != settings.allowed_user_id:
                return web.json_response({"error": "Доступ запрещён."}, status=403)

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Некорректный JSON."}, status=400)

        prompt = str(body.get("prompt", "")).strip()
        lang = str(body.get("lang", "ru")).lower()
        if not prompt:
            return web.json_response({"error": "Пустой промпт."}, status=400)
        if len(prompt) > settings.max_prompt_chars:
            return web.json_response(
                {"error": f"Промпт слишком длинный (макс. {settings.max_prompt_chars})."},
                status=400,
            )

        try:
            image_bytes, mime = await generate_image_flux(prompt, settings)
        except RateLimitError as exc:
            return web.json_response({"error": str(exc)}, status=429)
        except ImageGenerationError as exc:
            logger.error("HTTP generate failed: %s", exc)
            return web.json_response({"error": str(exc)}, status=502)

        b64 = base64.b64encode(image_bytes).decode("ascii")
        return web.json_response(
            {"image": f"data:{mime};base64,{b64}", "mime": mime, "prompt": prompt, "lang": lang}
        )

    app.router.add_get("/health", health)
    app.router.add_get("/prompts", prompts)
    app.router.add_post("/generate", generate)
    return app
