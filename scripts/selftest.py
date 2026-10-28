#!/usr/bin/env python3
"""Самопроверка бота без внешних служб.

Проверяет:
  1. Валидацию настроек окружения.
  2. Загрузку и нормализацию prompts.json.
  3. Разбор ответов Cloudflare (успех и ошибки).
  4. Генерацию изображения против локального mock-сервера Cloudflare.
  5. Проверку подписи initData Telegram.
  6. Клавиатуру и полный хэндлер web_app_data (успех + лимит + ошибки).

Запуск:
    python scripts/selftest.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import types as pytypes
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["BOT_TOKEN"] = "123456:TESTTOKEN"
os.environ["WEBAPP_URL"] = "https://mini.example.com"
os.environ["CLOUDFLARE_ACCOUNT_ID"] = "test-account"
os.environ["CLOUDFLARE_API_TOKEN"] = "test-token"

from aiohttp import web  # noqa: E402

from bot import handlers as handlers_mod  # noqa: E402
from bot import services  # noqa: E402
from bot.config import get_settings  # noqa: E402
from bot.handlers import _handle_generate, build_router  # noqa: E402
from bot.keyboards import gallery_keyboard  # noqa: E402
from bot.services import (  # noqa: E402
    CloudflareAPIError,
    PromptError,
    RateLimitError,
    load_prompts,
    verify_init_data,
)

PASSED = 0


def check(name: str, cond: bool) -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  \033[32m✓\033[0m {name}")
    else:
        print(f"  \033[31m✗\033[0m {name}")
        raise SystemExit(1)


# 1x1 transparent PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def start_mock_cloudflare() -> tuple[web.AppRunner, int]:
    async def run(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != "Bearer test-token":
            return web.json_response(
                {"errors": [{"code": 10000, "message": "Unauthorized"}]}, status=401
            )
        body = await request.json()
        prompt = str(body.get("prompt", ""))
        if prompt == "__RATE__":
            return web.json_response(
                {"errors": [{"code": 7003, "message": "Rate limited"}]}, status=429
            )
        if prompt == "__ERR__":
            return web.json_response(
                {"errors": [{"code": 5000, "message": "something broke"}]}, status=500
            )
        return web.json_response({"result": {"image": _PNG_B64}})

    app = web.Application()
    app.router.add_post("/", run)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return runner, port


def build_init_data(bot_token: str, fields: dict | None = None) -> str:
    fields = dict(fields or {"auth_date": str(int(time.time())), "id": "42", "first_name": "Test"})
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


# --------------------------------------------------------------------------- #
def test_settings() -> None:
    print("\n[1] Настройки окружения")
    settings = get_settings()
    check("BOT_TOKEN/WEBAPP_URL/Cloudflare задан", bool(settings.bot_token and settings.webapp_url))
    check("WEBAPP_URL — HTTPS", settings.webapp_url.startswith("https://"))
    check("FLUX_STEPS в диапазоне", 1 <= settings.flux_steps <= 8)

    saved = os.environ["WEBAPP_URL"]
    os.environ["WEBAPP_URL"] = "http://not-https.example.com"
    try:
        get_settings()
        check("Разрешает http:// WEBAPP_URL", False)
    except RuntimeError:
        check("Отклоняет http:// WEBAPP_URL", True)
    finally:
        os.environ["WEBAPP_URL"] = saved

    saved_token = os.environ["BOT_TOKEN"]
    os.environ["BOT_TOKEN"] = ""
    try:
        get_settings()
        check("Разрешает пустой BOT_TOKEN", False)
    except RuntimeError:
        check("Отклоняет пустой BOT_TOKEN", True)
    finally:
        os.environ["BOT_TOKEN"] = saved_token


def test_prompts() -> None:
    print("\n[2] Промпты")
    prompts = load_prompts(ROOT / "prompts.json")
    check("Загрузилось 8 промптов", len(prompts) == 8)
    first = prompts[0]
    check(
        "Нормализация: все ключи налицо",
        all(
            k in first
            for k in ("id", "theme", "title_ru", "title_en", "prompt_ru", "prompt_en", "preview_url")
        ),
    )
    check("RU/EN промпты непустые", bool(first["prompt_ru"]) and bool(first["prompt_en"]))

    tmp = ROOT / "tmp_prompts_test.json"
    tmp.write_text(json.dumps({"prompts": [{"theme": "x", "prompt": "hi"}]}), encoding="utf-8")
    try:
        items = load_prompts(tmp)
        check("Поддерживает {prompts: [...]}", len(items) == 1 and items[0]["prompt_ru"] == "hi")
    finally:
        tmp.unlink()

    tmp.write_text("{ not json", encoding="utf-8")
    try:
        load_prompts(tmp)
        check("Разрешает некорректный JSON", False)
    except PromptError:
        check("Отклоняет некорректный JSON", True)
    finally:
        tmp.unlink()


def test_cloudflare_parsing() -> None:
    print("\n[3] Разбор ответов Cloudflare")
    ok_body = json.dumps({"result": {"image": _PNG_B64}}).encode()
    out = services._decode_image_response(ok_body, "application/json")
    check("Декодирует base64-изображение", out == base64.b64decode(_PNG_B64))

    raw = services._decode_image_response(b"\x89PNG", "image/png")
    check("Пропускает raw image bytes", raw == b"\x89PNG")

    err = services._error_from_response(429, b'{"errors":[{"code":7003,"message":"rate"}]}')
    check("429 => RateLimitError", isinstance(err, RateLimitError))

    err2 = services._error_from_response(401, b'{"errors":[{"code":10000,"message":"Unauthorized"}]}')
    check("401 => CloudflareAPIError", isinstance(err2, CloudflareAPIError))

    try:
        services._decode_image_response(
            json.dumps({"errors": [{"message": "nope"}]}).encode(), "application/json"
        )
        check("Отсутствие image => ошибка", False)
    except CloudflareAPIError:
        check("Отсутствие image => ошибка", True)


async def test_generation(runner: web.AppRunner, port: int) -> None:
    print("\n[4] Генерация против mock-сервера")
    original = services.FLUX_ENDPOINT
    services.FLUX_ENDPOINT = f"http://127.0.0.1:{port}/"
    settings = get_settings()
    try:
        img, mime = await services.generate_image_flux("a cat", settings)
        check("Успешная генерация", img == base64.b64decode(_PNG_B64) and mime == "image/jpeg")

        try:
            await services.generate_image_flux("__RATE__", settings)
            check("Лимит => RateLimitError", False)
        except RateLimitError:
            check("Лимит => RateLimitError", True)

        try:
            await services.generate_image_flux("__ERR__", settings)
            check("Ошибка API => CloudflareAPIError", False)
        except CloudflareAPIError:
            check("Ошибка API => CloudflareAPIError", True)
    finally:
        services.FLUX_ENDPOINT = original


def test_init_data() -> None:
    print("\n[5] Проверка initData")
    token = "123456:TESTTOKEN"
    valid = build_init_data(token)
    ok, fields = verify_init_data(valid, token)
    check("Валидная подпись принимается", ok and fields.get("id") == "42")

    tampered = build_init_data(token, {"auth_date": str(int(time.time())), "id": "999"})
    ok2, _ = verify_init_data(tampered, "123456:WRONGTOKEN")
    check("Подпись с другим токеном отклоняется", not ok2)

    ok3, _ = verify_init_data("", token)
    check("Пустые данные отклоняются", not ok3)

    ok4, _ = verify_init_data("garbage=1&hash=zzz", token)
    check("Некорректный initData отклоняется", not ok4)


class _FakeWebAppData:
    def __init__(self, data: str) -> None:
        self.data = data


class _FakeMessage:
    def __init__(self, data: str) -> None:
        self.web_app_data = _FakeWebAppData(data)
        self.from_user = pytypes.SimpleNamespace(id=1)
        self.sent: list[tuple] = []

    async def answer(self, text: str = "", **kwargs) -> None:
        self.sent.append(("answer", text))

    async def answer_photo(self, photo=None, caption: str = "", **kwargs) -> None:
        self.sent.append(("photo", caption, photo))


def test_keyboard() -> None:
    print("\n[6] Клавиатура")
    settings = get_settings()
    kb = gallery_keyboard(settings.webapp_url)
    button = kb.keyboard[0][0]
    check("Содержит KeyboardButton с WebApp", button.web_app is not None)
    check("WebApp-url совпадает с WEBAPP_URL", button.web_app.url == settings.webapp_url)
    check("resize_keyboard включён", kb.resize_keyboard is True)


async def test_handler(settings) -> None:
    print("\n[7] Хэндлер web_app_data")
    keyboard = gallery_keyboard(settings.webapp_url)
    payload = json.dumps(
        {
            "action": "generate",
            "prompt": "a cyberpunk city",
            "lang": "ru",
            "theme": "cyberpunk",
            "theme_title": "Киберпанк",
        }
    )

    async def fake_generate(prompt, st):
        return base64.b64decode(_PNG_B64), "image/jpeg"

    original = handlers_mod.generate_image_flux
    handlers_mod.generate_image_flux = fake_generate
    try:
        msg = _FakeMessage(payload)
        await _handle_generate(msg, settings, keyboard)
        check("Успешный путь: отправлена photo", any(s[0] == "photo" for s in msg.sent))
        check("Успешный путь: без ошибок", not any("⚠️" in str(s[1]) for s in msg.sent))
        photo_call = next(s for s in msg.sent if s[0] == "photo")
        check("Caption содержит тему", "Киберпанк" in photo_call[1])
        check("Caption содержит язык", "Русский" in photo_call[1])
        check("Фото — BufferedInputFile", type(photo_call[2]).__name__ == "BufferedInputFile")

        msg2 = _FakeMessage(json.dumps({"action": "generate", "prompt": "   "}))
        await _handle_generate(msg2, settings, keyboard)
        check("Пустой промпт => сообщение об ошибке", any("пуст" in str(s[1]).lower() for s in msg2.sent))

        msg3 = _FakeMessage(json.dumps({"action": "nope"}))
        await _handle_generate(msg3, settings, keyboard)
        check("Неподдерживаемое действие => ошибка", any("неподдерживаемое" in str(s[1]).lower() for s in msg3.sent))

        msg4 = _FakeMessage("not-json")
        await _handle_generate(msg4, settings, keyboard)
        check("Некорректный JSON => ошибка", any("некорректны" in str(s[1]).lower() for s in msg4.sent))

        async def boom(*a, **k):
            raise RateLimitError("limit")

        handlers_mod.generate_image_flux = boom
        msg5 = _FakeMessage(payload)
        await _handle_generate(msg5, settings, keyboard)
        check("Лимит => сообщение о лимите", any("лимит" in str(s[1]).lower() for s in msg5.sent))
    finally:
        handlers_mod.generate_image_flux = original


async def amain() -> None:
    print("\n=== Самопроверка Photo Generator Bot ===")
    test_settings()
    test_prompts()
    test_cloudflare_parsing()
    test_init_data()
    test_keyboard()

    runner, port = await start_mock_cloudflare()
    try:
        await test_generation(runner, port)
    finally:
        await runner.cleanup()

    settings = get_settings()
    await test_handler(settings)

    router = build_router(settings)
    check("Router построен с хэндлерами", len(router.observers) >= 1)
    check("Наличие хэндлера сообщений", "message" in router.observers)

    print(f"\n\033[32m=== Успех: {PASSED} проверок пройдено ===\033[0m\n")


if __name__ == "__main__":
    asyncio.run(amain())
