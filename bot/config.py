"""Настройки окружения бота.

Все значения читаются из переменных окружения (см. .env.example).
В production рекомендуется задавать их через secrets-менеджер хостинга,
а не хранить в коде.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Полностью разрешённые настройки приложения."""

    bot_token: str
    webapp_url: str
    cloudflare_account_id: str
    cloudflare_api_token: str
    prompts_path: Path
    flux_steps: int
    http_timeout: int
    max_prompt_chars: int
    allowed_user_id: int | None
    # Опциональный прямой HTTP API бота (для Mini App без sendData).
    http_host: str | None
    http_port: int
    http_cors_origin: str | None

    @property
    def webapp_base(self) -> str:
        return self.webapp_url.rstrip("/")

    @property
    def http_enabled(self) -> bool:
        return bool(self.http_host)


def _int_env(name: str, default: int, *, low: int | None = None, high: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} должен быть числом, получено: {raw!r}") from exc
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def get_settings() -> Settings:
    """Собрать и валидировать настройки из окружения."""

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    webapp_url = os.getenv("WEBAPP_URL", "").strip()
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()

    problems: list[str] = []
    if not bot_token:
        problems.append("BOT_TOKEN не задан.")
    if not webapp_url:
        problems.append("WEBAPP_URL не задан (HTTPS-адрес Mini App).")
    if not account_id:
        problems.append("CLOUDFLARE_ACCOUNT_ID не задан.")
    if not api_token:
        problems.append("CLOUDFLARE_API_TOKEN не задан.")

    if problems:
        raise RuntimeError("Некорректные настройки окружения:\n  - " + "\n  - ".join(problems))

    if not webapp_url.startswith("https://"):
        raise RuntimeError("WEBAPP_URL должен начинаться с https:// — Mini App требует HTTPS.")

    allowed_raw = os.getenv("ALLOWED_USER_ID", "").strip()
    allowed_user_id = int(allowed_raw) if allowed_raw.isdigit() else None

    http_host = os.getenv("BOT_API_HOST", "").strip() or None

    return Settings(
        bot_token=bot_token,
        webapp_url=webapp_url,
        cloudflare_account_id=account_id,
        cloudflare_api_token=api_token,
        prompts_path=Path(os.getenv("PROMPTS_PATH", str(PROJECT_ROOT / "prompts.json"))),
        flux_steps=_int_env("FLUX_STEPS", 4, low=1, high=8),
        http_timeout=_int_env("HTTP_TIMEOUT", 120, low=10),
        max_prompt_chars=_int_env("MAX_PROMPT_CHARS", 2000, low=1, high=2048),
        allowed_user_id=allowed_user_id,
        http_host=http_host,
        http_port=_int_env("BOT_API_PORT", 8080, low=1, high=65535),
        http_cors_origin=(os.getenv("BOT_API_CORS_ORIGIN", "").strip() or None),
    )
