## Telegram support bot for Remnawave panel

Стек: Python 3.12, aiogram 3, PostgreSQL, Redis, SQLAlchemy async.

### Возможности

**Пользователь:**
- `/start` — приветствие и меню (FAQ, Создать обращение, Мои обращения)
- Любое сообщение в личку (текст, фото, медиа) → пересылается админам в рамках текущего открытого тикета или создаётся новый тикет
- Кнопка **FAQ** — показ редактируемого текста FAQ
- Кнопка **Создать обращение** — режим «напиши сообщение» → отправка в поддержку
- Кнопка **Мои обращения** — список последних 10 тикетов (номер, статус open/closed, дата обновления)

**Админ:**
- Под каждым сообщением тикета — кнопки **Ответить** и **Закрыть**
- **Ответить** — следующим сообщением отправить текст пользователю (логируется в этот тикет)
- **Закрыть** — перевести тикет в статус `closed`; следующие сообщения пользователя пойдут в новый тикет
- Ответ реплаем на сообщение тикета в чате с ботом — текст уходит пользователю и пишется в тот же тикет
- `/reply <user_id> [текст]` — ответ пользователю (если текст не указан — бот попросит отправить следующим сообщением)
- `/faq` — показать текущий FAQ
- `/setfaq [текст]` — обновить FAQ (файл `bot/faq.md`); если текст не указан — бот попросит отправить следующим сообщением

**Общее:**
- Логирование всех сообщений в PostgreSQL (таблицы `users`, `tickets`, `messages`)
- Админам при каждом сообщении пользователя показывается сводка по подписке из Remnawave API (статус, дни до конца, трафик, ссылка)
- FSM: ответ админа, создание обращения пользователем, редактирование FAQ
- Конфиг через env

### Архитектура

- **Точка входа**: `bot/main.py` — настройки, БД, Remnawave-клиент, middlewares, роутеры, polling
- **Конфиг**: `bot/config.py` (env → Pydantic Settings)
- **Middlewares**: `settings`, `remnawave`, `DbSession` (сессия на апдейт, commit/rollback)
- **Routers**:
  - `common` — `/start` (разное приветствие для админа и пользователя; у пользователя — меню)
  - `user` — сообщения и callback-кнопки пользователя (FAQ, Мои обращения, Создать обращение; пересылка в тикет)
  - `admin` — callback-кнопки (Ответить/Закрыть), `/reply`, `/faq`, `/setfaq`, ответ реплаем на тикет
- **FSM** (`bot/fsm/states.py`): `AdminReply`, `UserNewTicket`, `AdminFaqEdit`
- **БД**: модели в `bot/db/models.py` (`users`, `tickets`, `messages`); таблицы создаются миграциями Alembic при старте (`alembic upgrade head`)
- **Remnawave**: `bot/services/remnawave.py` — клиент панели; при необходимости адаптируйте под ваш API

### Структура проекта

```
bot/
  main.py          # точка входа
  config.py
  faq.md           # текст FAQ (редактируется /setfaq или вручную)
  routers/         # common, user, admin
  middlewares/
  fsm/
  db/
  services/
  utils/           # support_format, keyboards, faq
alembic/           # миграции БД
Dockerfile
docker-compose.yml
.env.example
```

### Деплой (Docker)

1. Скопируйте `.env.example` в `.env` и заполните:
   - `BOT_TOKEN` — токен бота от @BotFather
   - `ADMIN_IDS` — Telegram user id админов через запятую
   - `DATABASE_URL` — для docker-compose: `postgresql+asyncpg://postgres:postgres@db:5432/support_bot`
   - `REDIS_URL` — для docker-compose: `redis://redis:6379/0`
   - `REMNAWAVE_API_BASE_URL`, `REMNAWAVE_API_TOKEN` (и при необходимости `REMNAWAVE_CADDY_API_KEY`)

2. Запуск:

```bash
docker compose up --build -d
```

При старте контейнера бота выполняется `alembic upgrade head`, затем `python -m bot`.

3. Локальный запуск без Docker: поднимите PostgreSQL и Redis, задайте в `.env` соответствующие `DATABASE_URL` и `REDIS_URL`, выполните миграции и запустите бота:

```bash
alembic upgrade head
python -m bot
```

### Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота (обязательно) |
| `ADMIN_IDS` | ID админов через запятую (обязательно) |
| `DATABASE_URL` | URL БД, например `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | URL Redis для FSM (если пусто — FSM в памяти, сбрасывается при рестарте) |
| `REMNAWAVE_API_BASE_URL` | Базовый URL API панели |
| `REMNAWAVE_API_TOKEN` | Токен API панели |
| `REMNAWAVE_CADDY_API_KEY` | Опционально, если панель за Caddy Auth |
| `LOG_LEVEL` | Уровень логов (по умолчанию `INFO`) |

Для docker-compose также используются `POSTGRES_*` для сервиса `db` (см. `.env.example`).

### Redis (FSM)

Если задан `REDIS_URL`, состояние FSM хранится в Redis и сохраняется при рестартах бота. Если не задан — используется память (при рестарте состояния сбрасываются).

### Remnawave API `bot/services/remnawave.py` используется эндпоинт `GET /api/users/by-telegram-id/{telegramId}` и поля `status`, `expireAt`, `subscriptionUrl`, `userTraffic.usedTrafficBytes`. При другой схеме API измените клиент и/или `.env`.
