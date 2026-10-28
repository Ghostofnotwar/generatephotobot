#!/usr/bin/env bash
# Локальный/production запуск бота из корня проекта.
set -euo pipefail
cd "$(dirname "$0")"

# Выбираем интерпретатор: по умолчанию python3, переопределяем через PYTHON.
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

# Синхронизируем промпы для Mini App перед запуском.
"$PY" scripts/sync_prompts.py

exec "$PY" -m bot.main
