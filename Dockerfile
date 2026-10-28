FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала зависимости — для кэширования слоёв при смене кода.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Код бота, статика Mini App и промпы.
COPY bot/ ./bot/
COPY webapp/ ./webapp/
COPY prompts.json ./
COPY scripts/ ./scripts/

# Гарантируем, что webapp/prompts.json совпадает с корневым prompts.json.
RUN python scripts/sync_prompts.py

# Прямой HTTP API бота (если включен через BOT_API_HOST).
EXPOSE 8080

CMD ["python", "-m", "bot.main"]
