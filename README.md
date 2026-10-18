# QR Omissions

Сервис для выдачи подписанных QR-пропусков гостям и одноразовой регистрации на мероприятии организатором через Telegram-бота.

## Быстрый запуск

1. Скопируйте `.env.example` в `.env` и задайте `BOT_TOKEN`, `TOKEN_SECRET` и `ADMIN_API_KEY`.
2. Запустите приложение:

```bash
docker compose up --build
```

Compose ждёт готовности PostgreSQL, после чего контейнер приложения выполняет `alembic upgrade head` и запускает FastAPI на `http://localhost:8000`.

Проверка состояния:

```bash
curl http://localhost:8000/health
```

## Переменные окружения

`DATABASE_URL` задаёт SQLAlchemy URL базы; `BOT_TOKEN` — токен Telegram-бота; `TOKEN_SECRET` — секрет HMAC-SHA256; `ADMIN_API_KEY` — ключ заголовка `X-Admin-Key`; `ORGANIZER_TELEGRAM_IDS` — разделённый запятыми список Telegram ID организаторов; `CHECKIN_POINTS`, `BONUS_MIN_POINTS`, `BONUS_MAX_POINTS` задают правила начисления. `RUN_TELEGRAM_BOT=1` включает polling-бота в lifespan FastAPI (для API-only локальных тестов можно указать `0`).

## Архитектура

- `app/models.py` содержит SQLAlchemy-модели гостей, check-in и журнала транзакций.
- `app/security/tokens.py` выпускает QR-токены формата `qr1.payload.signature` и проверяет HMAC-подпись.
- `app/services/guests.py` хранит бизнес-правила: карточка гостя, одноразовый check-in и бонусы.
- `app/bot.py` реализует Telegram-сценарии и распознавание QR через OpenCV, включая ручной ввод токена.
- `app/api.py` предоставляет healthcheck, административное создание гостя и получение карточки по токену.
- `migrations/versions/001_initial.py` создаёт таблицы и ограничения в PostgreSQL.

## Сценарии

Администратор создаёт гостя через защищённый API:

```bash
curl -X POST http://localhost:8000/admin/guests \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-Key: replace-with-an-admin-api-key' \
  -d '{"name":"Иван Петров","category":"speaker","telegram_id":123456789}'
```

Ответ содержит `token`, который гость получает как PNG QR по команде `/qr`. Организатор отправляет боту фотографию QR, бот показывает имя, категорию, текущие баллы и статус. Нажатие check-in создаёт запись один раз и начисляет `CHECKIN_POINTS`; повторное сканирование остаётся идемпотентным. Ручной бонус проверяется по заданному диапазону и записывается в журнал с причиной.

Для получения карточки внутренним клиентом:

```bash
curl --get http://localhost:8000/guests/by-token --data-urlencode 'token=qr1....'
```

## Разработка и тесты

Локально установите зависимости `pip install -e '.[dev]'`, затем выполните `pytest`. Для миграций используйте `alembic upgrade head`; URL берётся из `DATABASE_URL`.

Тесты проверяют подпись и tamper-resistance токенов, round-trip QR, авторизацию организатора и администратора, одноразовость check-in, диапазон бонусов и сумму журнала начислений. Перед публикацией также выполняется smoke-check Compose и `/health`.

## Использование ИИ

Codex применялся для проектирования слоёв, написания кода и документации. После каждого логического шага выполнялись целевые проверки, просмотр diff и проверка отсутствия секретов. Решения по границам API, транзакциям, одноразовости и проверке QR были вручную просмотрены и исправлены; секреты из `.env` в репозиторий не добавлялись.

## Публикация

Репозиторий: https://github.com/SumTeaJay/QR-omissions. Для отправки изменений используйте атомарные коммиты после прохождения проверок.
