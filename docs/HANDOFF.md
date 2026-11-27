# HANDOFF — текущее состояние проекта

**Обновлено:** 2026-11-27
**Обновил:** agent (OpenCode)
**Ветка:** `main` (= `origin/main`); ветка `task/S1-06-logging-disk-guard` смержена

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
| S1-07 и далее | не начаты |
| Тесты / lint | 75 passed; Ruff без замечаний |

Worker забирает только переданные ему статусы и обработчики; до появления реальных шагов конвейера он не запускается в приложении. Захват и увеличение `attempt_count` атомарны в `BEGIN IMMEDIATE`; TTL 15 минут очищается при старте и опросе очереди. Ошибки повторяются до `queue.max_attempts`, затем фиксируются как `failed` вместе с событием и одним уведомлением через интерфейс notifier.

S1-08 добавляет `core/scheduler.py`: asyncio-задачи с интервалом или ежедневным временем в `settings.tz`, SQLite lease-lock с expiry и heartbeat, структурные логи и одно уведомление при ошибке job.

S1-06 добавляет два модуля ядра:

- `core/logging.py` — `JsonFormatter` (поля `event`, `timestamp`, `level` + `clip_id`, `stage`, `duration_ms`, `error`; трейсбек уходит в `error`) и `configure_logging(level, log_dir, rotation_mb, backups)`: stdout всегда, файл `logs/shorteditor.log` через `RotatingFileHandler` при заданном `log_dir`. Прежний `bot/logging.py` удалён, импорт переведён на `core.logging`.
- `core/disk.py` — `DiskUsage`, `read_disk_usage()`, `format_bytes()` и `DiskGuard.check() -> bool`. Алерт отправляется, когда свободно строго меньше `notifications.disk_free_alert_percent`, не чаще `notifications.disk_alert_repeat_hours`; событие `disk_space_low` пишется в лог всегда при срабатывании. При возврате места выше порога троттлинг сбрасывается (событие `disk_space_recovered`), поэтому следующее падение снова даёт алерт. Если notifier упал, алерт не считается отправленным и повторяется на следующей проверке.

Конфиг: добавлен `notifications.disk_alert_repeat_hours` (по умолчанию 6, минимум 1), `disk_free_alert_percent` ограничен 1–100. `AppSettings.log_level` теперь `None` по умолчанию: уровень берётся из `LOG_LEVEL`, иначе из `logging.level`.

Приложение: `config.yaml` читается один раз на старте и **необязателен** — при отсутствии файла действуют дефолты `AppConfig` (это снимает падение в контейнере, где конфига нет). Логи с ротацией настраиваются сразу. Job `disk_check` регистрируется по умолчанию, поэтому планировщик теперь запускается всегда — с одним `disk_check`, если других jobs не передали; путь для проверки — каталог БД (`data/`).

Проверки S1-06: `python -m pytest -q` — 75 passed; `python -m ruff check .` — без замечаний; `python -c "import shorteditor.bot"` — успешно.

## 3. Что НЕ проверено

- Реальное Telegram polling с действительным токеном и Telegram API не проверено.
- Доставка алерта о диске в Telegram проверена только на fake notifier; живая отправка не выполнялась.
- Ротация проверена конфигурацией handler'а (`maxBytes`, `backupCount`), а не реальным переполнением файла под нагрузкой.
- Троттлинг алертов живёт в памяти: после рестарта возможен повторный алерт раньше, чем через `disk_alert_repeat_hours`.
- Поведение после `kill -9` проверено имитацией старого `claimed_at` и перезапуском worker, но не реальным убийством процесса.
- SQLite advisory-lock проверен на одном процессе; конкурентная работа двух реальных процессов на одном файле SQLite не проверялась.
- Реальные parser/digest/TTL jobs пока не передаются приложению; проверены расписания и lifecycle scheduler.
- Реальное кеширование модели Whisper: volume `/models` и `HF_HOME=/models` настроены, но модель ещё не скачивалась (появится в S3-03).
- Рендер `.ass` через `ass=` — до S3-06 нечего проверять.
- Запуск под пользователем `app` на Linux-сервере с bind-mount: на Docker Desktop Windows права маскируются, на Ubuntu возможны проблемы с владельцем `./data`. Проверить при первом деплое на сервер.
- `config.yaml` не копируется в образ и не монтируется в Compose. Теперь это не роняет старт (дефолты), но настройки поведения из файла в контейнере не применяются — решить до подключения конвейера в S2.
- Docker-образ после S1-06 не пересобирался: код ядра импортируется, но `logs/` в контейнере создаётся на лету; volume `logs` в Compose уже есть.

## 4. Следующий шаг

**S1-07 · CI: линт и тесты** (`docs/TASKS.md`).
Открывать первым: новый `.github/workflows/ci.yml`; зависимости уже описаны в `pyproject.toml` (`.[test,dev]`), локальный прогон — 75 тестов, Ruff чистый.
Порядок этапа 1: S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S1-08 → S1-06 → **S1-07**.

## 5. Публикация

`main` запушен под аккаунтом `fowgsl123-dev` (приглашение в `fedorshibeko8-bot/shortEditor` с правами write принято 2026-11-27). Схема работы: ветка `task/<ID>-<кратко>` → PR → merge в `main`; журналы обновляются в том же PR.

## 6. Окружение

- Windows, рабочий каталог `C:\Users\Vladimir\Desktop\нови проект\shortEditor`.
- Python 3.12.10, виртуальное окружение `venv/` в корне (в git не попадает).
- Docker Desktop + Engine 29.9.3, Compose CLI v5.7.0.
- pytest 9.2.0, 75 тестов; Ruff 0.11+.

## 7. Как проверить, что проект «жив»

```bash
python -m pytest -q
python -m ruff check .
docker compose config --quiet
docker build -t shorteditor:dev -f docker/Dockerfile .
docker run --rm shorteditor:dev sh -c "ffmpeg -version | head -1; fc-match 'Montserrat ExtraBold'"
docker run --rm shorteditor:dev; echo "exit=$?"
```

Ожидаемо: 75 passed, Ruff чистый, конфиг валиден, ffmpeg 5.1.x, `Montserrat-ExtraBold.ttf`, последняя команда — `Startup error: required environment variables ...` и `exit=1`.

---

_Шаблон для следующего обновления (не удалять):_
```
Обновлено: <дата> · <агент> · ветка <branch>
Сделано: <ID> — <кратко>
Осталось: <ID> — с чего продолжить, какой файл открыть первым
Блокеры: <...>
```
