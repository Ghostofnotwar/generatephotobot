# 🎨 Photo Generator Bot

Telegram-бот с встроенным **Mini App** для генерации изображений. Пользователь открывает галерею
превью по темам (Хэллоуин, киберпанк, фэнтези, стимпанк, готика, sci-fi, аниме, природа),
выбирает карточку — и промпт подставляется автоматически. После редактирования и нажатия
«Сгенерировать» бот зовёт **Cloudflare Workers AI** (модель `FLUX.1 Schnell`) и отправляет
готовое изображение в чат.

---

## ✨ Возможности

- **Галерея превью** с поддержкой RU/EN и переключателем языка промпта.
- **Авто-подстановка промпта** при выборе карточки темы.
- **Редактирование промпта**, счётчик символов, поиск по темам, «случайный» промпт.
- **Генерация** через Cloudflare Workers AI (`@cf/black-forest-labs/flux-1-schnell`).
- **Отправка изображения** пользователю в чат с промптом-описанием.
- **Понятные ошибки**: лимит запросов, недоступность API, слишком длинный промпт.
- **Два режима связи** Mini App ↔ бот: `Telegram.WebApp.sendData` (по умолчанию) и прямой HTTP API.
- **Docker** и простые deploy-инструкции для любого хостинга.

---

## 🗂 Структура проекта

```
generatephotobot/
├── bot/                    # aiogram-бот
│   ├── config.py           # настройки окружения + валидация
│   ├── services.py         # промпты + Cloudflare Workers AI + проверка initData
│   ├── keyboards.py        # reply-клавиатура с WebApp-кнопкой
│   ├── handlers.py         # хэндлеры /start, /help, web_app_data
│   ├── http_server.py      # опциональный прямой HTTP API (/generate, /prompts)
│   └── main.py             # точка входа (polling + optional HTTP)
├── webapp/                 # статический Mini App
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── config.js           # apiBase для прямого HTTP-режима
│   ├── manifest.json
│   ├── prompts.json        # копия корневого (синхронизируется скриптом)
│   └── previews/           # превью тем (локальные изображения)
├── prompts.json            # canonical: превью + промпты (RU/EN)
├── scripts/
│   └── sync_prompts.py     # копирует prompts.json в webapp/
├── requirements.txt
├── .env.example
├── Dockerfile
└── run.sh
```

---

## 🧱 Технологический стек

| Коллекция | Технология |
| --- | --- |
| Бот | Python 3.11+, `aiogram` 3.x (асинхронный) |
| Mini App | HTML + CSS + vanilla JS (+ Telegram WebApp SDK) |
| Генерация | Cloudflare Workers AI — `@cf/black-forest-labs/flux-1-schnell` |
| Хранение | `prompts.json` (статический JSON) |
| Деплой | Бот — Docker/Railway/Fly.io/VPS; Mini App — Cloudflare Pages/Vercel/GitHub Pages |

---

## 🚀 Quick start

### 1. Подготовьте Cloudflare Workers AI

1. Зарегистрируйтесь на [cloudflare.com](https://cloudflare.com) и создайте аккаунт.
2. В dashboard нажмите **Workers AI** → **Get started** (или **Model catalog**).
3. Убедитесь, что модель `FLUX.1 Schnell` доступна (на бесплатном тарифе даётся ~10k neuron/день).
4. Найдите **Account ID** (в sidebar слева).
5. Создайте **API token** с правом **Workers AI: Edit** (не deploy-only!). Токен создаётся в
   menu **My Profile → API Tokens**.

### 2. Получите токен бота

Стартовый диалог с [@BotFather](https://t.me/BotFather): `/newbot` → получите токен и @username.

### 3. Разверните Mini App (статический хостинг)

Загрузите содержимое папки `webapp/` на любой статический хостинг с HTTPS:

- **Cloudflare Pages** — выберите проект, каталог `webapp/`, framework preset — *None*.
- **Vercel** — фолдер `webapp/`, build command — не задавать, output — `webapp` (или просто upload).
- **GitHub Pages** — отметьте `webapp/` как корень проекта для Pages.

Дождитесь publish и получите HTTPS-адрес, например `https://your-miniapp.example.com`.

> В `webapp/` уже лежит `prompts.json` и `previews/`. Если вы изменили `prompts.json` в корне,
> перезапустите `python scripts/sync_prompts.py` и перезалейте.

### 4. Запустите бота

Скопируйте `.env.example` → `.env` и заполните:

```bash
cp .env.example .env
# редактировать .env
```

Запустите локально:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/sync_prompts.py
python -m bot.main
```

Или через Docker:

```bash
docker build -t photo-bot .
docker run --env-file .env -p 8080:8080 photo-bot
```

На Railway/Fly.io/VPS используйте `run.sh` или `python -m bot.main` с заданными переменными окружения.

### 5. Проверьте

Нажмите кнопку «Открыть галерею промптов», выберите тему, нажмите «Сгенерировать» — изображение
придёт в чат бота.

---

## ⚙️ Переменные окружения

| Переменная | Обязательно | Описание |
| --- | --- | --- |
| `BOT_TOKEN` | ✅ | Токен бота от @BotFather |
| `WEBAPP_URL` | ✅ | HTTPS-адрес Mini App |
| `CLOUDFLARE_ACCOUNT_ID` | ✅ | Account ID Cloudflare |
| `CLOUDFLARE_API_TOKEN` | ✅ | API token с правом Workers AI |
| `FLUX_STEPS` | — | Diffusion-шаги, 1–8 (по умолчанию `4`) |
| `HTTP_TIMEOUT` | — | Таймаут HTTP-запроса к Cloudflare (по умолчанию `120`) |
| `MAX_PROMPT_CHARS` | — | Максимум знаков промпта (по умолчанию `2000`) |
| `PROMPTS_PATH` | — | Путь к canonical `prompts.json` |
| `ALLOWED_USER_ID` | — | Если задан — бот отвечает только этому пользователю |
| `BOT_API_HOST` | — | Если задан (например `0.0.0.0`) — поднимается прямой HTTP API |
| `BOT_API_PORT` | — | Порт HTTP API (по умолчанию `8080`) |
| `BOT_API_CORS_ORIGIN` | — | Origin Mini App для CORS прямого API |

---

## 🔌 Как связаны Mini App и бот

**Режим по умолчанию — `Telegram.WebApp.sendData`.**

1. Бот отправляет сообщение с **reply-клавиатурой**, содержащей `KeyboardButton` + `WebAppInfo`
   (кнопка «Открыть галерею промптов»).
2. Пользователь жмёт кнопку → открывается Mini App.
3. Пользователь выбирает тему и жмёт «Сгенерировать».
4. Mini App вызывает `Telegram.WebApp.sendData(JSON)`. Telegram отправляет боту
   **сервисное сообщение** с полем `web_app_data`.
5. Бот (`WebAppDataFilter`) разбирает JSON, вызывает Cloudflare, отправляет изображение в чат.
6. Mini App закрывается автоматически.

> ⚠️ `sendData` работает **только** для кнопок **reply keyboard** (не inline-кнопок) и ограничена
> **4096 байт**. Наши промпты сильно меньше, так что это не проблема.

**Режим прямого HTTP (опциональный).**

Если задан `BOT_API_HOST`, бот поднимает HTTP API:

- `GET /health` — проверка живости.
- `GET /prompts` — список промптов.
- `POST /generate` — генерация. Запрос должен содержать заголовок
  `X-Telegram-Init-Data: Telegram.WebApp.initData`; сервер **проверяет подпись HMAC-SHA256**.

Включите его в `webapp/config.js`, задав `apiBase`:

```js
window.BOT_CONFIG = { apiBase: "https://your-bot.example.com" };
```

Теперь Mini App POST-ит промпт напрямую и сам отображает результат (не закрывается). Это нужно
для промптов >4096 байт или если Mini App открыт не из reply-клавиатуры.

---

## 📝 Формат prompts.json

```json
{
  "id": 1,
  "theme": "halloween",
  "title_ru": "Хэллоуин",
  "title_en": "Halloween",
  "prompt_ru": "...",
  "prompt_en": "...",
  "preview_url": "previews/halloween.jpg",
  "tags": ["хэллоуин", "осень"]
}
```

- `preview_url` — относительный путь к превью внутри `webapp/`.
- Дополнительно поддерживаются поля `steps` и `seed` (опционально).
- Файл может быть как массивом объектов, так и объектом с ключом `prompts`.

---

## 🐛 Проблемы и решения

| Симптом | Причина / Решение |
| --- | --- |
| `403` / «недоступен Workers AI» | Токен — deploy-only. Создайте токен с правом **Workers AI: Edit**. |
| `429` / «лимит истек» | Исчерпан дневной лимит нейронов. Подождите или подключите тариф. |
| Кнопка не открывает Mini App | `WEBAPP_URL` должен быть **HTTPS** и доступным из интернета. |
| `sendData` не работает | Используйте **reply keyboard** (как в `keyboards.py`), не inline-кнопку. |
| `prompts.json` не грузится в Mini App | Залейте в корень развертывания Mini App и синхронизируйте скриптом. |
| Бот не отвечает | Проверьте `ALLOWED_USER_ID`, если он задан. |

---

## 🛠 Локальная разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните реальными ключами
python scripts/sync_prompts.py
python -m bot.main
```

Mini App можно открыть в браузере для быстрого тестирования UI — функция `sendData` будет
недоступна (только в Telegram), но галерея и подстановка промптов работают.

---

## 📜 Лок

MIT.
