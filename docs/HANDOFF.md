# HANDOFF — текущее состояние проекта

**Обновлено:** 2026-11-28
**Обновил:** agent (OpenCode)
**Ветка:** `main` (= `origin/main`); ветка `task/S2-01-twitch-client` смержена

## 1. Что это за проект

Telegram-бот ищет Twitch-клипы ≤ 60 сек, передаёт их админу на одобрение, монтирует вертикальное видео 1080×1920 с русскими субтитрами и загружает мастер в Cloudflare R2.
Полное ТЗ: `docs/SPEC.md` v1.2. Целевой объём — 3–5 видео/день на 2 vCPU / 4 GB.

## 2. Статус

| Задача/компонент | Состояние |
|---|---|
| CR-001, S0-04, S1-01, S1-02 | **done** |
| S1-03 — Docker-образ и compose | **done**, собрано и проверено |
| S1-04 — Скелет бота | **done**, проверено локально и в контейнере |
| S1-05 — Worker-loop и очередь из БД | **done**, смержено и проверено |
| S1-08 — Планировщик фоновых задач | **done**, смержено и проверено |
| S1-06 — Логирование и диск-гард | **done**, смержено и проверено |
| S1-07 — CI: линт и тесты | **done**, workflow добавлен, локально и на Python 3.11 проверен |
| S2-01 — Клиент Twitch Helix | **done**, смержено и проверено |
| S2-02 и далее | не начаты |
| Тесты / lint | 91 passed; Ruff без замечаний |

Worker забирает только переданные ему статусы и обработчики; до появления реальных шагов конвейера он не запускается в приложении. Захват и увеличение `attempt_count` атомарны в `BEGIN IMMEDIATE`; TTL 15 минут очищается при старте и опросе очереди. Ошибки повторяются до `queue.max_attempts`, затем фиксируются как `failed` вместе с событием и одним уведомлением через интерфейс notifier.

S1-08 добавляет `core/scheduler.py`: asyncio-задачи с интервалом или ежедневным временем в `settings.tz`, SQLite lease-lock с expiry и heartbeat, структурные логи и одно уведомление при ошибке job.

S1-06 добавляет два модуля ядра:

- `core/logging.py` — `JsonFormatter` (обязательные `event`, `timestamp`, `level` плюс все дополнительные атрибуты записи: `clip_id`, `stage`, `duration_ms`, `error`, `job`, `reason` и т. п.; несериализуемые значения приводятся к строке, трейсбек уходит в `error`, `timestamp` — время создания записи) и `configure_logging(level, log_dir, rotation_mb, backups)`: stdout всегда, файл `logs/shorteditor.log` через `RotatingFileHandler` при заданном `log_dir`. Прежний `bot/logging.py` удалён, импорт переведён на `core.logging`.
- `core/disk.py` — `DiskUsage`, `read_disk_usage()`, `format_bytes()` и `DiskGuard.check() -> bool`. Алерт отправляется, когда свободно строго меньше `notifications.disk_free_alert_percent`, не чаще `notifications.disk_alert_repeat_hours`; событие `disk_space_low` пишется в лог всегда при срабатывании. При возврате места выше порога троттлинг сбрасывается (событие `disk_space_recovered`), поэтому следующее падение снова даёт алерт. Если notifier упал, алерт не считается отправленным и повторяется на следующей проверке.

Конфиг: добавлен `notifications.disk_alert_repeat_hours` (по умолчанию 6, минимум 1), `disk_free_alert_percent` ограничен 1–100. `AppSettings.log_level` теперь `None` по умолчанию: уровень берётся из `LOG_LEVEL`, иначе из `logging.level`.

Приложение: `config.yaml` читается один раз на старте и **необязателен** — при отсутствии файла действуют дефолты `AppConfig` (это снимает падение в контейнере, где конфига нет). Логи с ротацией настраиваются сразу. Job `disk_check` регистрируется по умолчанию, поэтому планировщик теперь запускается всегда — с одним `disk_check`, если других jobs не передали; путь для проверки — каталог БД (`data/`).

Проверки S1-06: `python -m pytest -q` — 77 passed; `python -m ruff check .` — без замечаний; `python -c "import shorteditor.bot"` — успешно.

S1-07 добавляет `.github/workflows/ci.yml`: push в `main`, `pull_request` и ручной запуск; один job на `ubuntu-latest` с Python 3.11 (как в `docker/Dockerfile`), кэш pip по `pyproject.toml`, `permissions: contents: read`, concurrency с отменой устаревших прогонов, таймаут 10 минут. Шаги: установка `.[test,dev]`, `python -m ruff check .`, `python -m pytest -q`. Тот же прогон выполнен в контейнере `python:3.11-slim` — 77 passed, Ruff чистый; `.github/workflows/ci.yml` распарсен и проверен по ключевым полям.

S2-01 добавляет `parser/twitch.py`: app token cache с 60-секундным запасом и `asyncio.Lock`, один повтор после 401, ограниченные retry 429/5xx (`Retry-After`, затем `Ratelimit-Reset`, экспоненциальный бэкофф), typed mapping клипа и пагинация с пределами страниц/клипов. HTTP-настройки — `parser.http_timeout_seconds` (10) и `parser.http_max_attempts` (3), aiohttp добавлен явной зависимостью. Клиент не читает `.env` и не подключён к другим компонентам. Проверки: 91 passed локально и в `python:3.11-slim`, Ruff чистый, импорты без сети.

## 3. Что НЕ проверено

- Реальное Telegram polling с действительным токеном и Telegram API не проверено.
- Доставка алерта о диске в Telegram проверена только на fake notifier; живая отправка не выполнялась.
- Ротация проверена конфигурацией handler'а (`maxBytes`, `backupCount`), а не реальным переполнением файла под нагрузкой.
- Троттлинг алертов живёт в памяти: после рестарта возможен повторный алерт раньше, чем через `disk_alert_repeat_hours`.
- Поведение после `kill -9` проверено имитацией старого `claimed_at` и перезапуском worker, но не реальным убийством процесса.
- SQLite advisory-lock проверен на одном процессе; конкурентная работа двух реальных процессов на одном файле SQLite не проверялась.
- Реальные parser/digest/TTL jobs пока не передаются приложению; проверены расписания и lifecycle scheduler.
- Реальный запрос к Twitch с боевыми ключами, фактический rate limit и поведение при длительном 429 не проверялись (реальный запрос не запускался и не нужен для unit-тестов).
- Реальное кеширование модели Whisper: volume `/models` и `HF_HOME=/models` настроены, но модель ещё не скачивалась (появится в S3-03).
- Рендер `.ass` через `ass=` — до S3-06 нечего проверять.
- Запуск под пользователем `app` на Linux-сервере с bind-mount: на Docker Desktop Windows права маскируются, на Ubuntu возможны проблемы с владельцем `./data`. Проверить при первом деплое на сервер.
- `config.yaml` не копируется в образ и не монтируется в Compose. Теперь это не роняет старт (дефолты), но настройки поведения из файла в контейнере не применяются — решить до подключения конвейера в S2.
- CI-workflow проверен на GitHub: первый прогон `46062818232` — зелёный за 23 секунды (кэш pip и таймауты в норме). После обновления экшенов до Node.js 24 (`actions/checkout@v7`, `actions/setup-python@v7`) выполнен повторный прогон. Branch protection не настраивался: обязательность проверки в настройках репозитория не включена.
- Docker-образ после S1-06 пересобирался: в контейнере пишется `logs/shorteditor.log` с extra-полями, запуск без env даёт exit 1.

## 4. Следующий шаг

**S2-02 · Фильтры и дедупликация** (`docs/TASKS.md`).
Открывать первым: карточку S2-02, затем `src/shorteditor/parser/twitch.py` (клиент уже готов) и `src/shorteditor/core/config.py` (`parser.*`). Этап 1 закрыт: S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S1-08 → S1-06 → S1-07; этап 2 начат с S2-01.

## 5. Публикация

`main` запушен под аккаунтом `fedorshibeko8-bot` (gh auth active, токен со scope `repo` и `workflow`). Схема работы: ветка `task/<ID>-<кратко>` → PR или локальный merge в `main`; журналы обновляются в том же PR/коммите.

## 6. Окружение

- Windows, рабочий каталог `C:\Users\Lenovo\Desktop\shortEditor`.
- Python 3.15.2 (пакет требует ≥ 3.11; прод-образ и CI — 3.11).
- Docker Desktop + Engine 29.9.3, Compose CLI v5.7.0.
- pytest 9.2.0, 91 тест; Ruff 0.11+.

## 7. Как проверить, что проект «жив»

```bash
python -m pytest -q
python -m ruff check .
docker compose config --quiet
docker build -t shorteditor:dev -f docker/Dockerfile .
docker run --rm shorteditor:dev sh -c "ffmpeg -version | head -1; fc-match 'Montserrat ExtraBold'"
docker run --rm shorteditor:dev; echo "exit=$?"
```

Ожидаемо: 91 passed, Ruff чистый, конфиг валиден, ffmpeg 5.1.x, `Montserrat-ExtraBold.ttf`, последняя команда — `Startup error: required environment variables ...` и `exit=1`.

---

_Шаблон для следующего обновления (не удалять):_
```
Обновлено: <дата> · <агент> · ветка <branch>
Сделано: <ID> — <кратко>
Осталось: <ID> — с чего продолжить, какой файл открыть первым
Блокеры: <...>
```
