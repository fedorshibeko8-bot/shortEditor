# HANDOFF — текущее состояние проекта

**Обновлено:** 2026-11-25
**Обновил:** Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776
**Ветка:** `gr0knemthiswor1d-lab-shorteditor-project-task` (переименование app-инструментом в `task/S1-03-docker` недоступно: ветка уже переименовывалась в этой сессии)

## 1. Что это за проект

Telegram-бот ищет Twitch-клипы ≤ 60 сек, передаёт их админу на одобрение, монтирует вертикальное видео 1080×1920 с русскими субтитрами и загружает мастер в Cloudflare R2.
Полное ТЗ: `docs/SPEC.md` v1.2. Целевой объём — 3–5 видео/день на 2 vCPU / 4 GB.

## 2. Статус

| Задача/компонент | Состояние |
|---|---|
| CR-001, S0-04, S1-01, S1-02 | **done** |
| S1-03 — Docker-образ и compose | **blocked**: Docker Engine не запущен, образ не собран |
| Пакетирование src-layout | `pip install -e .` и импорты проходят |
| Compose-файл | `docker compose config --quiet` проходит |
| Тесты / lint | 28 тестов прошли; Ruff прошёл |
| S1-04 и далее | не начаты |

## 3. S1-03: реализовано и не проверено

Добавлены Dockerfile на `python:3.11-slim-bookworm`, entrypoint с LF, compose с единственной службой `app`, `.dockerignore`, пакетирование setuptools, тома `data/`, `logs/`, `models/` и `HF_HOME=/models`.
Команда по умолчанию — `sleep infinity`, а не фиктивный бот. После реализации точки входа в S1-04 надо заменить `command` сервиса `app` в `docker-compose.yml` на реальную команду запуска бота.

В `docker/fonts/` находятся статические экземпляры Montserrat ExtraBold (вес 800) и Inter Black (вес 900), созданные из официальных variable TTF Google Fonts; рядом сохранены соответствующие OFL-тексты лицензий. Dockerfile устанавливает их, затем запускает `fc-cache -f`.

Проверки на этой машине:
- Python 3.15.2: `pip install -e .` успешно; `import shorteditor, aiosqlite, yaml` печатает `ok`.
- `docker compose config --quiet`: успешно; Docker Compose CLI v5.7.0.
- `pytest -q`: 28 passed.
- Ruff: All checks passed.
- Docker CLI 29.9.3 установлен, но Docker Engine недоступен: отсутствует pipe `//./pipe/dockerDesktopLinuxEngine`.
- `docker build`, запуск контейнера, ffmpeg/libass, `fc-list`, размер образа и длительность сборки **не проверены**. Версия ffmpeg внутри образа неизвестна.

После запуска Docker Engine выполнить:
`docker build -t shorteditor:dev . -f docker/Dockerfile`;
`docker compose config`;
`docker compose up -d --build`;
проверить `ffmpeg -version`, наличие фильтра `ass`, `fc-list` для Montserrat/Inter и импорт `shorteditor`, `aiosqlite`, `yaml`.
Для проверки сохранения моделей создать файл-маркер в `./models`, выполнить `docker compose up -d --force-recreate app` и убедиться, что маркер доступен внутри `/models`; `HF_HOME` должен быть `/models`.

## 4. Следующий шаг

Сначала разблокировать и завершить проверку S1-03 на работающем Docker Engine; только затем переходить к **S1-04 · Скелет бота**.
Открывать первым: `docker/Dockerfile`, `docker-compose.yml`, `docs/TASKS.md`.

Порядок этапа 1:
S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S1-08 → S1-06 → S1-07.

## 5. Публикация

Ранее push в `fedorshibeko8-bot/shortEditor` блокировался 403: credential авторизовался как `gr0knemthiswor1d-lab` с недостаточными правами. Публикацию изменений S1-03 нужно повторить после устранения прав доступа.
