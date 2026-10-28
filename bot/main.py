"""Точка входа: запуск aiogram-бота (и опционально HTTP API).

Запуск:
    python -m bot.main
или (из корня проекта):
    python -m bot.main
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from .config import get_settings
from .handlers import build_router

logger = logging.getLogger("photobot")


async def _start_http_api(settings) -> object | None:
    from aiohttp import web

    from .http_server import create_app

    app = create_app(settings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.http_host, settings.http_port)
    await site.start()
    logger.info("HTTP API запущен: http://%s:%s", settings.http_host, settings.http_port)
    return runner


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    settings = get_settings()

    bot = Bot(settings.bot_token, parse_mode="HTML")
    dp = Dispatcher()
    dp.include_router(build_router(settings))

    runner = await _start_http_api(settings) if settings.http_enabled else None

    logger.info("Запускаем polling бота…")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if runner is not None:
            await runner.cleanup()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
