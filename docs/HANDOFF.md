# HANDOFF — текущее состояние проекта

**Обновлено:** 2026-11-26
**Обновил:** agent (merge/verify)
**Ветка:** `main` (= `origin/main`); ветка `task/S1-04-bot-skeleton` смержена

## 1. Что это за проект

Telegram-бот ищет Twitch-клипы ≤ 60 сек, передаёт их админу на одобрение, монтирует вертикальное видео 1080×1920 с русскими субтитрами и загружает мастер в Cloudflare R2.
Полное ТЗ: `docs/SPEC.md` v1.2. Целевой объём — 3–5 видео/день на 2 vCPU / 4 GB.

## 2. Статус

| Задача/компонент | Состояние |
|---|---|
| CR-001, S0-04, S1-01, S1-02 | **done** |
| S1-03 — Docker-образ и compose | **done**, собрано и проверено |
| S1-04 — Скелет бота | **done**, проверено локально и в контейнере |
| S1-05 и далее | не начаты |
| Тесты / lint | 31 passed; Ruff без замечаний |

Сборка образа: `docker build -t shorteditor:dev -f docker/Dockerfile .`, образ `shorteditor:dev` ~872 МБ, `python:3.11-slim-bookworm`.

Проверено внутри образа:
- `ffmpeg version 5.1.9-0+deb12u1`, фильтр `ass` (libass) присутствует.
- `fc-list` видит Montserrat (style ExtraBold) и Inter (style Black).
- `python -c "import shorteditor, aiosqlite, yaml, pydantic"` — ок.
- `aiogram 3.34.0`, `python -c "import shorteditor.bot"` не запускает polling.
- без обязательных env: понятное сообщение и exit code 1 (без трейсбека); с недействительным токеном — `Startup error: Telegram server says - Unauthorized`, exit 1.
- `/status` на пустой БД отдаёт честные нули по всем статусам.
- процесс под пользователем `app` (uid 1000), `/app/data` и `/models` доступны на запись.
- `docker compose config --quiet` — ок.

В образе и в Compose теперь единая команда запуска: `python -m shorteditor.bot` (заглушка `sleep infinity` убрана из `docker/Dockerfile` и `docker-compose.yml`).

**Исправленный при проверке баг:** `fc-match "Montserrat ExtraBold"` возвращал `DejaVuSans.ttf`, то есть libass молча подменял бы шрифт. Добавлен `docker/fonts/fonts.conf` с fontconfig-алиасами; после пересборки `fc-match` возвращает `Montserrat-ExtraBold.ttf` и `Inter-Black.ttf`. Решение записано в D-018.

## 3. Что НЕ проверено

- Реальное Telegram polling с действительным токеном и Telegram API не проверено.
- Graceful shutdown по SIGINT/SIGTERM проверен только чтением кода: без живого polling не на чем проверить. Проверить при первом запуске с реальным токеном (в логах `bot_shutdown_requested` → `bot_shutdown_complete`).
- Реальное кеширование модели Whisper: volume `/models` и `HF_HOME=/models` настроены, но модель ещё не скачивалась (появится в S3-03).
- Рендер `.ass` через `ass=` — до S3-06 нечего проверять.
- Запуск под пользователем `app` на Linux-сервере с bind-mount: на Docker Desktop Windows права маскируются, на Ubuntu возможны проблемы с владельцем `./data`. Проверить при первом деплое на сервер.

## 4. Следующий шаг

**S1-05 · Worker-loop и очередь из БД** (`docs/TASKS.md`).
Открывать первым: `src/shorteditor/core/worker.py`, `src/shorteditor/pipeline/`, `src/shorteditor/storage/repository.py`.
Скелет бота завершён: точка входа `python -m shorteditor.bot`, middleware и `/start`/`/status` готовы.
Порядок этапа 1 сохраняется: S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S1-08 → S1-06 → S1-07.

## 5. Публикация

`main` запушен под аккаунтом `fedorshibeko8-bot`. Агент в worktree не может пушить: его credential — `gr0knemthiswor1d-lab`, ответ 403. Схема работы: реализация в worktree → мерж, проверка и push из `C:\Users\Lenovo\Desktop\shortEditor`.

## 6. Окружение

- Windows, основной каталог `C:\Users\Lenovo\Desktop\shortEditor`.
- Worktree Copilot: `C:\Users\Lenovo\.copilot\repos\copilot-worktrees\shortEditor\gr0knemthiswor1d-lab-super-train` (ветка `gr0knemthiswor1d-lab-shorteditor-project-task`).
- Python 3.15.2 (пакет требует ≥ 3.11; образ на 3.11 — расхождение версий учитывать в тестах).
- Docker Desktop + Engine 29.9.3, Compose CLI v5.7.0.
- pytest 9.2.0, 31 тест.

## 7. Как проверить, что проект «жив»

```bash
python -m pytest -q
docker compose config --quiet
docker build -t shorteditor:dev -f docker/Dockerfile .
docker run --rm shorteditor:dev sh -c "ffmpeg -version | head -1; fc-match 'Montserrat ExtraBold'"
docker run --rm shorteditor:dev; echo "exit=$?"
```

Ожидаемо: 31 passed, конфиг валиден, ffmpeg 5.1.x, `Montserrat-ExtraBold.ttf`, последняя команда — `Startup error: required environment variables ...` и `exit=1`.

---

_Шаблон для следующего обновления (не удалять):_
```
Обновлено: <дата> · <агент> · ветка <branch>
Сделано: <ID> — <кратко>
Осталось: <ID> — <с чего продолжить, какой файл открыть первым>
Блокеры: <...>
```
