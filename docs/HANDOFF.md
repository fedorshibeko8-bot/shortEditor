# HANDOFF — текущее состояние проекта

**Обновлено:** 2026-11-25
**Обновил:** agent (merge/publish) — после Copilot App fdb2bb91
**Ветка:** `main` (работа из `gr0knemthiswor1d-lab-shorteditor-project-task` смержена)

## 1. Что это за проект

Telegram-бот ищет Twitch-клипы ≤ 60 сек, передает их админу на одобрение, монтирует вертикальное видео 1080×1920 с русскими субтитрами и загружает мастер в Cloudflare R2.
Полное ТЗ: `docs/SPEC.md` v1.2. Целевой объём — 3–5 видео/день на 2 vCPU / 4 GB.

## 2. Статус

| Что | Состояние |
|---|---|
| Этап 0 — каркас репозитория | **done** |
| CR-001 — правки SPEC v1.2 | **done** |
| S0-04 — служебные файлы репозитория | **done** |
| S1-01 — слой конфигурации | **done** |
| S1-02 — схема БД и машина статусов | **done** |
| Схема конфига SPEC v1.2 | синхронизирована |
| Тесты | pytest зелёный локально |
| Docker / compose | не проверялись |
| FFmpeg | не проверялся |

## 3. Где остановились

Применён CR-001. В репозитории есть MIT LICENSE, `.editorconfig`, PR-шаблон и обновленные журналы.
S1-01 включает загрузку `.env`, валидацию `config.yaml`, ручную перезагрузку `ConfigManager.reload()` и unit-тесты.
Автоматический watcher и вызов перезагрузки из `/filters` относятся к S2-04.
S1-02 завершена: SQLite-схема включает clips/renders/events, миграции идемпотентны, реализованы клип-статусы, поле sent_to_admin_at, индекс TTL и атомарный claim/release задачи.
Следующая задача — S1-03. S1-03 и последующие задачи этапа не начаты.

**Публикация выполнена.** Ветка смержена в `main` (`4fe2611`) и запушена в `origin` из основного каталога под аккаунтом `fedorshibeko8-bot`. Блокер 403 из истории относился к другому GitHub-аккаунту, под которым авторизовался worktree Copilot; из `C:\Users\Lenovo\Desktop\shortEditor` push проходит. Локальная ветка `gr0knemthiswor1d-lab-shorteditor-project-task` оставлена как есть (worktree ещё существует), в `origin` её нет.

## 4. Следующая задача

**S1-03 · Docker-образ и compose** (`docs/TASKS.md`).
Открывать первым: `docker/`, `pyproject.toml` и раздел среды в `docs/SPEC.md`.

Порядок этапа 1:
S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S1-08 → S1-06 → S1-07.

## 5. Решения, которые нельзя менять молча

Все — в `docs/DECISIONS.md`. Кратко: клипы ≤ 60 сек без тримминга; исходник не кропаем (`contain` + blur-фон); отказ только по клипу; LLM в v1 не участвует в таймкодах; субтитры идут через собственный `.ass` и libass.

## 6. Открытые вопросы к заказчику

Нет.

## 7. Окружение разработчика

- Windows-машина.
- Основной каталог (источник истины, отсюда идёт push): `C:\Users\Lenovo\Desktop\shortEditor`, аккаунт `fedorshibeko8-bot`.
- Worktree Copilot (там велась работа до merge): `C:\Users\Lenovo\.copilot\repos\copilot-worktrees\shortEditor\gr0knemthiswor1d-lab-super-train`.
- Python 3.15.2.
- pytest 9.2.0 (12 тестов, зелёные).
- git 2.56.
- GitHub CLI доступен.
- FFmpeg и Docker не проверялись.
- Целевая среда — Ubuntu 22.04+ / docker-compose.

## 8. Как проверить проект

- `python -m pytest -q`
- `python -c "from shorteditor.core.config import load_config; c=load_config('config.example.yaml'); print(c.render.fps, c.parser.candidate_ttl_hours, c.publish.retention_days)"`
- После появления Docker-файлов: `docker compose config` и `docker compose up`.
