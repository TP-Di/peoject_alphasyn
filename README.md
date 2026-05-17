# alphasyn

Бот, который раз в день читает Google Sheet с днями рождения, генерирует поздравление через Gemini и шлёт его в Telegram-группу.

## Структура

- `main.py` — one-shot: проверяет именинников **на сегодня** и отправляет поздравления. Внутри ретраи (`RETRY_ATTEMPTS=5`, `RETRY_DELAY=30*60`) только для упавших отправок.
- `scheduler.py` — обёртка с APScheduler, дёргает `main.py` каждый день в 09:00 Asia/Tashkent. Нужна только для compose-режима.
- `Dockerfile` — образ с Python 3.12 + зависимости.
- `docker-compose.yml` — вечно висящий сервис со встроенным шедулером.
- `.github/workflows/birthdays.yml` — GHA cron, запускает `python main.py` в 04:00 UTC (09:00 Ташкент).

## Переменные окружения

| Переменная | Что это |
|---|---|
| `TG_BOT_TOKEN` | Токен Telegram-бота |
| `TG_GROUP_ID` | ID чата/группы куда слать |
| `GEMINI_API_KEY` | Ключ Google Gemini |
| `GOOGLE_SA_JSON` | **Весь JSON** сервис-аккаунта одной строкой |
| `GOOGLE_ID` | ID Google Sheet |

Шаблон в `.env.example`. Для локального запуска положи реальные значения в `.env` (он в `.gitignore`).

## Сценарии запуска

### 1. GitHub Actions (рекомендую)

Ничего своего держать не нужно. Cron живёт в GHA, секреты — в Settings → Secrets and variables → Actions.

```
Settings → Secrets → New repository secret
  TG_BOT_TOKEN, TG_GROUP_ID, GEMINI_API_KEY, GOOGLE_SA_JSON, GOOGLE_ID
```

Workflow уже лежит в `.github/workflows/birthdays.yml`. Запустить руками — вкладка Actions → Daily birthdays → Run workflow.

**Минус:** GHA-cron не гарантирует точное время (может опаздывать на 5–30 мин под нагрузкой).

### 2. Локальный one-shot

Для теста или ручного дёрга.

```bash
# нативно
pip install -r requirements.txt
python main.py

# или через docker (образ собирается один раз)
docker build -t alphasyn .
docker run --rm --env-file .env alphasyn
```

После первой сборки повторные `docker run` используют кэш — пересборка только если поменялись `requirements.txt`, `Dockerfile` или `main.py`.

### 3. Host cron + docker

VPS с docker, без compose. Системный cron раз в день стартует контейнер, контейнер отрабатывает и умирает. Никаких висящих процессов.

Собрать один раз:
```bash
docker build -t alphasyn /path/to/repo
```

Положить `.env` рядом, добавить в `crontab -e`:
```cron
0 9 * * * docker run --rm --env-file /path/to/repo/.env alphasyn >> /var/log/alphasyn.log 2>&1
```

Образ висит в локальном кэше docker, пересборка только при изменениях:
```bash
cd /path/to/repo && git pull && docker build -t alphasyn .
```

### 4. Docker Compose (вечно висящий)

Один долгоживущий контейнер, внутри APScheduler сам триггерит задачу. Удобно если уже есть compose-стек на сервере и нет cron.

```bash
docker compose up -d --build   # первый раз
docker compose logs -f         # смотреть логи
```

Дальше:
- `docker compose up -d` без `--build` — поднять с **существующим** образом (мгновенно, без пересборки).
- `docker compose build` — пересобрать **только** когда поменялся `Dockerfile` или `requirements.txt`. Слой с `pip install` кэшируется отдельно от копирования `main.py`, поэтому правка `main.py` не запускает переустановку зависимостей.
- `docker compose restart birthdays` — после правки `main.py` (volume не монтируется, нужен `up -d --build` чтобы код попал в образ; либо добавь `volumes: - ./:/app` если хочешь правки на лету).

`restart: unless-stopped` поднимет контейнер обратно после ребута хоста или падения процесса.

**Минусы compose-режима vs GHA/cron:**
- Контейнер должен всегда работать. Если процесс упал и `restart` не сработал — задача не выполнится.
- Память постоянно занята (немного, но всё же).
- Сложнее в эксплуатации (логи, мониторинг healthcheck).

## Поведение ретраев

В `main.py`:
- `fetch_birthdays()` тянет список с Sheets. При ошибке — повторная попытка через `RETRY_DELAY` (30 мин).
- `send_one()` — генерация + отправка для одного человека. Успешные удаляются из очереди, упавшие ретраятся.
- После 5 неудачных попыток подряд — `exit 1` со списком неотправленных.

В GHA это покрасит запуск в красный, в compose APScheduler просто залогирует и подождёт следующего дня.
