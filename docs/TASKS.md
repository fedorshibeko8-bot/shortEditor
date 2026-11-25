# Журнал задач

Единый борд проекта. Источник истины по тому, **что сделано, что в работе и что дальше**.
Правила ведения — в `AGENTS.md` §3–§5. Здесь только статусы и факты; обсуждения — в `docs/DECISIONS.md`.

**Легенда статусов:** `todo` · `in_progress` · `blocked` · `review` · `done`
**Последнее обновление:** 2026-11-25 · CR-001, S0-04, S1-01 и S1-02 завершены; S1-03 заблокирована проверкой Docker Engine.

---

## Сводка

| Этап | Задач | done | in_progress | blocked | todo |
|---|---:|---:|---:|---:|---:|
| 0. Каркас репозитория | 4 | 4 | 0 | 0 | 0 |
| 1. Каркас приложения | 8 | 2 | 0 | 1 | 5 |
| 2. Парсер | 5 | 0 | 0 | 0 | 5 |
| 3. Конвейер | 10 | 0 | 0 | 0 | 10 |
| 4. Публикация | 4 | 0 | 0 | 0 | 4 |
| 5. Доработки | 4 | 0 | 0 | 0 | 4 |
| **Итого** | **35** | **6** | **0** | **1** | **28** |

---

## Этап 0 · Каркас репозитория

### S0-01 · Структура каталогов и базовые файлы
- status: done
- owner: agent (scaffold), 2026-11-25
- depends on: —
- area: корень, `src/`, `tests/`, `docker/`, `scripts/`, `data/`
- acceptance:
  - [x] каталоги под модули bot/parser/pipeline/storage/core
  - [x] `.gitignore`, `.env.example`, `config.example.yaml`
  - [x] `README.md`

### S0-02 · Документация проекта
- status: done
- owner: agent (scaffold), 2026-11-25
- depends on: S0-01
- area: `docs/`, `AGENTS.md`
- acceptance:
  - [x] `docs/SPEC.md` v1.1 с уточнениями заказчика (§8)
  - [x] `docs/ARCHITECTURE.md` — карта модулей и инварианты
  - [x] `docs/DECISIONS.md` — ADR-лог
  - [x] `AGENTS.md` — протокол передачи контекста между агентами

### S0-03 · Инициализация git и публикация на GitHub
- status: done
- owner: agent (scaffold), 2026-11-25
- depends on: S0-01, S0-02
- area: `.git/`, remote
- acceptance:
  - [x] `git init`, первый коммит
  - [x] репозиторий создан на GitHub, `main` запушен

### S0-04 · Служебные файлы репозитория
- status: done
- owner: Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776, 2026-11-25
- depends on: —
- area: `LICENSE`, `.editorconfig`, `.github/PULL_REQUEST_TEMPLATE.md`
- acceptance:
  - [x] `LICENSE` добавлен (см. §6.1)
  - [x] `.editorconfig` добавлен (см. §6.2)
  - [x] PR-шаблон добавлен (см. §6.3) и содержит чеклист обновления журналов

---

## Этап 1 · Каркас приложения

### S1-01 · Слой конфигурации
- status: done
- owner: Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776, 2026-11-25
- depends on: —
- area: `src/shorteditor/core/config.py`, `pyproject.toml`
- acceptance:
  - [x] `.env` читается через pydantic-settings, отсутствие обязательного ключа — понятная ошибка на старте
  - [x] `config.yaml` валидируется по схеме; значения по умолчанию соответствуют `config.example.yaml`
  - [x] ручная перезагрузка ConfigManager.reload() реализована; автоматический watcher и вызов из /filters относятся к S2-04
  - [x] unit-тесты на валидацию и дефолты

### S1-02 · Схема БД и машина статусов
- status: done
- owner: Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776, 2026-11-25
- depends on: S1-01
- area: `src/shorteditor/storage/`, `src/shorteditor/core/statuses.py`
- acceptance:
  - [x] таблица `clips` (+ `renders`, `events`/лог), миграции идемпотентны
  - [x] переходы статусов валидируются; недопустимый переход — исключение
  - [x] атомарный «захват» задачи воркером (без двойной обработки)
  - [x] unit-тесты на все переходы из §2.3 ТЗ
  - [x] поле `clips.sent_to_admin_at` и индекс по `(status, sent_to_admin_at)` для скана TTL

### S1-03 · Docker-образ и compose
- status: blocked
- owner: Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776, 2026-11-25
- depends on: S1-01
- area: `docker/`, `docker-compose.yml`, `pyproject.toml`
- acceptance:
  - [x] Dockerfile на python:3.11-slim-bookworm, устанавливает ffmpeg/fontconfig/ca-certificates, пакет и шрифты OFL Montserrat ExtraBold/Inter Black; создаёт app uid 1000
  - [ ] образ собран; внутри `ffmpeg -version`, фильтр `ass` присутствует, `fc-list` видит оба семейства
  - [x] compose описывает data/logs/models volume, optional `.env`, TZ и одну службу `app`
  - [x] `docker compose config` проходит; команда по умолчанию — `sleep infinity`, а не фиктивный бот
  - [x] кеш моделей постоянный (`./models:/models`, `HF_HOME=/models`); нет загрузки моделей на этапе сборки
  - [x] `pip install -e .` и импорты `shorteditor`, `aiosqlite`, `yaml` проходят
  - [ ] запуск и пересоздание контейнера проверены на работающем Docker Engine

### S1-04 · Скелет бота (aiogram 3)
- status: todo
- owner: —
- depends on: S1-01, S1-03
- area: `src/shorteditor/bot/`
- acceptance:
  - [ ] middleware блокирует всех, кроме `TELEGRAM_ADMIN_ID`
  - [ ] `/start`, `/status` отвечают
  - [ ] структурные логи, корректный graceful shutdown
  - [ ] тест middleware «чужой id → отказ»

### S1-05 · Worker-loop и очередь из БД
- status: todo
- owner: —
- depends on: S1-02, S1-03
- area: `src/shorteditor/core/worker.py`, `src/shorteditor/pipeline/`
- acceptance:
  - [ ] цикл берёт задачу из SQLite, не держит состояние в памяти
  - [ ] ретраи до 3, затем `failed` + событие для уведомления
  - [ ] ограничение параллельности из конфига (по умолчанию 1)
  - [ ] после kill -9 и рестарта незавершённая задача подхватывается
  - [ ] снятие протухших `worker_claim`: TTL claim'а (новый ключ `queue.claim_ttl_minutes`, по умолчанию 15) проверяется при старте и периодически; иначе упавший воркер навсегда блокирует клип
  - [ ] increment `attempt_count` при каждой попытке шага, сброс при успехе
  - [ ] integration-тест с фейковым шагом пайплайна

### S1-06 · Логирование и диск-гард
- status: todo
- owner: —
- depends on: S1-01
- area: `src/shorteditor/core/logging.py`, `core/disk.py`
- acceptance:
  - [ ] JSON-логи с полями `clip_id`, `stage`, `duration_ms`, `error`; ротация
  - [ ] проверка свободного места, при < 10 % — событие алерта (раз в N часов, без спама)
  - [ ] unit-тесты на формат и на порог

### S1-07 · CI: линт и тесты
- status: todo
- owner: —
- depends on: S1-01
- area: `.github/workflows/ci.yml`, `pyproject.toml`
- acceptance:
  - [ ] ruff + pytest на push/PR, зелёный на пустом проекте
  - [ ] кэш зависимостей, прогон ≤ 3 мин

### S1-08 · Планировщик фоновых задач
- status: todo
- owner: —
- depends on: S1-01, S1-02, S1-05
- area: `src/shorteditor/core/scheduler.py`
- acceptance:
  - [ ] in-process планировщик (asyncio, без внешних брокеров) с джобами: опрос парсера раз в `parser.poll_interval_minutes`, ежедневная сводка, скан TTL кандидатов (раз в 10 мин), проверка диска
  - [ ] защита от двойного запуска при двух инстансах (advisory-lock через строку в SQLite)
  - [ ] джоба, упавшая с ошибкой, не убивает планировщик; ошибка логируется и попадает в уведомления
  - [ ] unit-тест на расчёт следующего запуска и на пропуск джобы при занятом локе

---

## Этап 2 · Парсер

### S2-01 · Клиент Twitch Helix
- status: todo
- owner: —
- depends on: S1-01, S1-05
- area: `src/shorteditor/parser/twitch.py`
- acceptance:
  - [ ] app access token с автообновлением
  - [ ] `GET /clips` с пагинацией, `first`/`after`, соблюдение rate limit (429 → бэкофф)
  - [ ] за интерфейсом, моки в тестах

### S2-02 · Фильтры и дедупликация
- status: todo
- owner: —
- depends on: S2-01, S1-02
- area: `src/shorteditor/parser/filters.py`
- acceptance:
  - [ ] фильтры из §3.1: категории, каналы, просмотры, `duration ≤ 60`, свежесть 24 ч, whitelist/blacklist, ключевые слова
  - [ ] повторный `clip_id` не создаёт запись
  - [ ] unit-тесты на границы (60 сек — включительно)

### S2-03 · Карточка кандидата в TG
- status: todo
- owner: —
- depends on: S2-01, S1-04
- area: `src/shorteditor/bot/handlers/`, `bot/keyboards/`
- acceptance:
  - [ ] превью, автор, категория, длительность, просмотры, ссылка
  - [ ] кнопки «Одобрить»/«Отклонить», идемпотентная обработка callback (двойной клик)
  - [ ] статус меняется на `sent_to_admin`, затем `approved`/`rejected`
  - [ ] скачивание не стартует до одобрения

### S2-04 · Редактирование фильтров из TG
- status: todo
- owner: —
- depends on: S2-02, S1-04
- area: `src/shorteditor/bot/handlers/filters.py`
- acceptance:
  - [ ] `/filters` показывает текущие значения
  - [ ] изменение сохраняется в `config.yaml` (или overlay) и применяется без рестарта
  - [ ] валидация ввода, понятные ошибки админу

### S2-05 · TTL карточек модерации №1
- status: todo
- owner: —
- depends on: S2-03, S1-02, S1-08
- area: `src/shorteditor/bot/handlers/`, `src/shorteditor/parser/`
- acceptance:
  - [ ] в `clips` есть `sent_to_admin_at`; TTL из `parser.candidate_ttl_hours`
  - [ ] по истечении: статус `rejected`, причина `expired`, карточка редактируется без кнопок
  - [ ] поздний клик по старой карточке не меняет статус (idempotent callback)
  - [ ] просроченные не попадают в сводку как ручные отказы

---

## Этап 3 · Конвейер

### S3-01 · Скачивание клипа
- status: todo
- owner: —
- depends on: S1-05, S2-03
- area: `src/shorteditor/pipeline/download.py`
- acceptance:
  - [ ] yt-dlp качает MP4 в `data/downloads/<clip_id>/`, проверка что файл валиден (ffprobe)
  - [ ] ретраи до 3, таймаут, очистка мусора при ошибке
  - [ ] статус `downloading` → `transcribing`

### S3-02 · Извлечение аудио
- status: todo
- owner: —
- depends on: S3-01
- area: `src/shorteditor/pipeline/audio.py`
- acceptance:
  - [ ] ffmpeg → WAV 16 kHz mono в `data/audio/`
  - [ ] unit-тест на команду, integration — на коротком сэмпле

### S3-03 · Транскрипция (интерфейс + faster-whisper)
- status: todo
- owner: —
- depends on: S3-02, S1-01
- area: `src/shorteditor/pipeline/transcribe.py`
- acceptance:
  - [ ] `transcribe(audio) -> list[Word]` с `start`, `end`, `text`
  - [ ] модель/язык/`word_timestamps` из конфига, `initial_prompt` и `glossary` применяются
  - [ ] транскрипт сохраняется в БД (для переделки без повторного ASR)
  - [ ] провайдер подменяем (stub в тестах)
  - [ ] реализация триггера fallback строго по §3.4 ТЗ v1.2
  - [ ] тест «fallback срабатывает один раз»

### S3-04 · Постобработка текста
- status: todo
- owner: —
- depends on: S3-03
- area: `src/shorteditor/pipeline/text.py`
- acceptance:
  - [ ] удаление филлеров/повторов без сдвига таймкодов
  - [ ] строки ≤ 25 символов и ≤ 6 слов, границы по словам
  - [ ] unit-тесты на русском: длинные слова, дефисы, эмодзи

### S3-05 · Генератор `.ass`
- status: todo
- owner: —
- depends on: S3-04, S1-01
- area: `src/shorteditor/pipeline/subtitles.py`
- acceptance:
  - [ ] karaoke-режим с тегами `\k` по словам; fallback — построчные фразы
  - [ ] стиль из конфига: шрифт, 68 px, обводка 5 px, позиция 60 % высоты
  - [ ] корректные таймкоды `h:mm:ss.cc`, экранирование спецсимволов
  - [ ] snapshot-тесты на готовый `.ass`

### S3-06 · Рендер одним проходом
- status: todo
- owner: —
- depends on: S3-05, S3-01, S1-03
- area: `src/shorteditor/pipeline/render.py`
- acceptance:
  - [ ] 1080×1920: размытая копия на весь кадр + исходник целиком (contain) + `ass=` субтитры
  - [ ] libx264 preset medium crf 20, AAC 192k, `-movflags +faststart`
  - [ ] исходник не кропается и не зумится
  - [ ] статус `rendering` → `sent_for_review`, файл в `data/rendered/`
  - [ ] `fps: auto`, не выше 60, с допустимым даунсемплом исходника 60 fps до 30 по конфигу

### S3-07 · Модерация №2 и переделка
- status: todo
- owner: —
- depends on: S3-06, S1-04
- area: `src/shorteditor/bot/handlers/review.py`
- acceptance:
  - [ ] отправка видео + кнопки «Опубликовать»/«На переделку»/«Отказ»
  - [ ] переделка: правка текста субтитров, karaoke on/off, хук → `rendering` без повторной транскрипции
  - [ ] отказ → `rejected`, TEMP удаляется, автор не банится
  - [ ] версии рендера сохраняются

### S3-08 · Обработка ошибок конвейера
- status: todo
- owner: —
- depends on: S1-05, S3-01, S3-06
- area: `src/shorteditor/pipeline/`, `src/shorteditor/core/`
- acceptance:
  - [ ] любой шаг → до 3 попыток, затем `failed` + уведомление с текстом ошибки
  - [ ] ошибка не блокирует очередь
  - [ ] integration-тест «падает скачивание» и «падает рендер»

### S3-09 · Контроль размера видео под лимит Telegram
- status: todo
- owner: —
- depends on: S3-06
- area: `src/shorteditor/pipeline/render.py`
- acceptance:
  - [ ] после рендера проверяется размер файла, при > 45 МБ — до 2 перекодирований `crf +4`
  - [ ] если всё равно > 45 МБ — отправка документом + предупреждение админу, модерация не блокируется
  - [ ] размер и итоговый `crf` пишутся в лог и в `meta.json`
  - [ ] unit-тест на логику шага (без реального кодирования, мок ffprobe/ffmpeg)

### S3-10 · Валидация готового рендера
- status: todo
- owner: —
- depends on: S3-06
- area: `src/shorteditor/pipeline/render.py`, `tests/integration/`
- acceptance:
  - [ ] ffprobe-проверки: 1080×1920, длительность = длительность входа ±0.5 с, видео h264, аудио aac, есть аудиодорожка
  - [ ] проверка «не покропали»: сравнение кадра исходника и кадра рендера по центральной полосе (SSIM/перцептивный хэш) выше порога, указанного в конфиге
  - [ ] при провале — шаг ретраится, затем `failed` с понятной причиной
  - [ ] валидация вынесена из S3-06 в отдельный шаг пайплайна

---

## Этап 4 · Публикация

### S4-01 · Клиент R2 и загрузка
- status: todo
- owner: —
- depends on: S3-06, S1-01
- area: `src/shorteditor/storage/r2.py`, `pipeline/publish.py`
- acceptance:
  - [ ] boto3 к R2, `YYYY/MM/DD/<clip_id>.mp4` + `meta.json`
  - [ ] `meta.json`: автор, ссылка на клип, канал, дата, статус, версия
  - [ ] ретраи, понятные ошибки; тест на замоканном S3
  - [ ] генерация `meta.json` строго по схеме §3.8 ТЗ v1.2
  - [ ] идемпотентная перезапись при повторной публикации версии

### S4-02 · Очистка TEMP и диск-гард в цикле
- status: todo
- owner: —
- depends on: S4-01, S1-06
- area: `src/shorteditor/pipeline/cleanup.py`
- acceptance:
  - [ ] после `published`/`rejected` каталог клипа удаляется полностью
  - [ ] логика не удаляет файлы других клипов и БД
  - [ ] при < 10 % свободного места — алерт админу

### S4-03 · Уведомления и ежедневная сводка
- status: todo
- owner: —
- depends on: S4-01, S1-04
- area: `src/shorteditor/bot/notifications.py`
- acceptance:
  - [ ] уведомления: новый кандидат, готовое видео, `failed`
  - [ ] сводка раз в сутки в `notifications.daily_digest_at`: найдено/одобрено/опубликовано
  - [ ] ссылка на объект в R2 в уведомлении о публикации
  - [ ] `expired`-клипы учитываются отдельной строкой, а не в «отклонено админом»

### S4-04 · E2E-прогон и замер производительности
- status: todo
- owner: —
- depends on: S4-01, S4-02, S4-03, S3-08
- area: `tests/integration/`, `docs/`
- acceptance:
  - [ ] полный цикл на тестовом клипе: найден → одобрен → отрендерен → в R2
  - [ ] рестарт в середине рендера не теряет задачу
  - [ ] замер: ≤ 15 мин на клип, 3–5 видео/день на 2 vCPU / 4 GB
  - [ ] результат замера записан в `docs/HANDOFF.md`

---

## Этап 5 · Доработки (после v1)

### S5-01 · Контентная классификация кандидатов
- status: todo
- owner: —
- depends on: S4-04
- area: `src/shorteditor/parser/` (+ внешняя модель)
- acceptance:
  - [ ] предварительный скоринг короткого листа кандидатов, порог в конфиге, флаг on/off

### S5-02 · LLM-нормализация субтитров (опционально)
- status: todo
- owner: —
- depends on: S3-05
- area: `src/shorteditor/pipeline/text.py`, `transcribe.py`
- acceptance:
  - [ ] `normalize(words) -> words` за флагом, число слов сохраняется (проверка выравниванием)
  - [ ] `temperature=0`, таймаут, fallback на сырой транскрипт при любом сбое
  - [ ] кэш по хэшу аудио+промпта, версия результата в БД
  - [ ] таймкоды не изменяются (тест)

### S5-03 · Расширенные стили и шаблоны хуков
- status: todo
- owner: —
- depends on: S3-05
- area: `src/shorteditor/pipeline/subtitles.py`, `config`
- acceptance:
  - [ ] набор пресетов стиля, шаблоны хуков, выбор из TG

### S5-04 · Публикация в соцсети
- status: todo
- owner: —
- depends on: S4-04
- area: `src/shorteditor/pipeline/`, новые интеграции
- acceptance:
  - [ ] отдельный ADR с выбором API и рисками ToS
  - [ ] публикация хотя бы в одну платформу, отключаемая флагом

---

## История (append-only)

Формат: `дата · ID · агент · что сделано · что осталось · следующий шаг`

```
2026-11-25 · S0-01..S0-03 · agent(scaffold) · создана структура каталогов, документация (SPEC v1.1, ARCHITECTURE, DECISIONS, AGENTS), шаблоны .env/config, git-инициализация, репозиторий на GitHub · разработка не начата · следующий шаг: S1-01 (слой конфигурации)
2026-11-25 · S1-01 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · реализованы pydantic-settings для `.env`, Pydantic-схемы YAML-конфига и явная перезагрузка `ConfigManager.reload()`; добавлены unit-тесты обязательных переменных, дефолтов, валидации и reload · нет блокеров · следующий шаг: S1-02 (схема БД и машина статусов)
2026-11-25 · S0-04 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · закрыты служебные файлы репозитория: MIT LICENSE, .editorconfig и PR-шаблон с чеклистом журналов · нет блокеров · следующий шаг: оставаться на S1-01 до завершения синхронизации схемы
2026-11-25 · S1-01 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · схема конфига синхронизирована с SPEC v1.2: candidate_ttl_hours, retention_days, fps и параметры размера рендера, отдельная LlmNormalizeConfig; добавлены тесты дефолтов и валидации · нет блокеров · следующий шаг: S1-02 (схема БД и машина статусов)
2026-11-25 · публикация · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · ветка и локальные коммиты готовы, тесты зелёные · push заблокирован GitHub 403 для учетной записи с недостаточными правами на репозиторий · следующий шаг: предоставить владельцу репозитория или аккаунту push-доступ, затем запушить ветку и открыть/смержить PR
2026-11-25 · S1-02 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · добавлены aiosqlite-схема clips/renders/events, идемпотентные миграции, поле sent_to_admin_at и индекс TTL, машина статусов и атомарный захват/освобождение задачи; unit-тесты матрицы статусов, миграции и claim выполнены · нет блокеров · следующий шаг: S1-03 (Docker-образ и compose)
2026-11-25 · S1-03 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · добавлены пакетирование src-layout, Dockerfile, Compose, entrypoint, .dockerignore, официальные шрифты Google Fonts и D-017; pip install -e ., compose config, 28 тестов и Ruff прошли · сборка/проверки контейнера заблокированы: Docker CLI 29.9.3 есть, но Linux Engine недоступен на named pipe `//./pipe/dockerDesktopLinuxEngine`; точные ffmpeg в образе, размер и время сборки неизвестны; локальное имя ветки осталось прежним, app-инструмент отказался повторно переименовывать ветку · следующий шаг: запустить Docker Engine, закончить проверки S1-03, затем S1-04
2026-11-25 · CR-001 · Copilot App fdb2bb91-6c82-4e74-82a8-1b26d76c9776 · применены правки SPEC v1.2, новые задачи S0-04/S1-08/S2-05/S3-09/S3-10, правки существующих задач, ADR D-012…D-016, структура ARCHITECTURE и служебные файлы LICENSE/.editorconfig/PR-template · нужно выполнить финальный чеклист и закоммитить handoff · следующий шаг: проверка секретов и diff перед двумя docs-коммитами
```
