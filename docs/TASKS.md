# Журнал задач

Единый борд проекта. Источник истины по тому, **что сделано, что в работе и что дальше**.
Правила ведения — в `AGENTS.md` §3–§5. Здесь только статусы и факты; обсуждения — в `docs/DECISIONS.md`.

**Легенда статусов:** `todo` · `in_progress` · `blocked` · `review` · `done`
**Последнее обновление:** 2026-11-25 · этап 0 завершён, этап 1 не начат.

> **Входящее изменение: CR-001 (open)** — `docs/CHANGES-v1.2.md`.
> ТЗ на правки документации: SPEC → v1.2, новые задачи S0-04, S1-08, S2-05, S3-09, S3-10, правки шести существующих задач, ADR D-012…D-016, служебные файлы репозитория.
> Выполняется **до** S1-01. Код приложения в рамках CR не пишется.

---

## Сводка

| Этап | Задач | done | in_progress | todo |
|---|---|---|---|---|
| 0. Каркас репозитория | 3 | 3 | 0 | 0 |
| 1. Каркас приложения | 7 | 0 | 0 | 7 |
| 2. Парсер | 4 | 0 | 0 | 4 |
| 3. Конвейер | 8 | 0 | 0 | 8 |
| 4. Публикация | 4 | 0 | 0 | 4 |
| 5. Доработки | 4 | 0 | 0 | 4 |
| **Итого** | **30** | **3** | **0** | **27** |

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

---

## Этап 1 · Каркас приложения

### S1-01 · Слой конфигурации
- status: todo
- owner: —
- depends on: —
- area: `src/shorteditor/core/config.py`, `pyproject.toml`
- acceptance:
  - [ ] `.env` читается через pydantic-settings, отсутствие обязательного ключа — понятная ошибка на старте
  - [ ] `config.yaml` валидируется по схеме; значения по умолчанию соответствуют `config.example.yaml`
  - [ ] фильтры парсера перечитываются без рестарта (watch/перезагрузка по команде)
  - [ ] unit-тесты на валидацию и дефолты

### S1-02 · Схема БД и машина статусов
- status: todo
- owner: —
- depends on: S1-01
- area: `src/shorteditor/storage/`, `src/shorteditor/core/statuses.py`
- acceptance:
  - [ ] таблица `clips` (+ `renders`, `events`/лог), миграции идемпотентны
  - [ ] переходы статусов валидируются; недопустимый переход — исключение
  - [ ] атомарный «захват» задачи воркером (без двойной обработки)
  - [ ] unit-тесты на все переходы из §2.3 ТЗ

### S1-03 · Docker-образ и compose
- status: todo
- owner: —
- depends on: S1-01
- area: `docker/`, `docker-compose.yml`, `pyproject.toml`
- acceptance:
  - [ ] образ на python:3.11-slim + ffmpeg + шрифты Montserrat/Inter
  - [ ] `fc-list` внутри контейнера видит оба шрифта
  - [ ] тома для `data/` и `logs/`, `.env` через env_file
  - [ ] `docker compose config` проходит, контейнер стартует

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
  - [ ] исходник не кропается и не зумится (проверка по кадрам/ffprobe)
  - [ ] статус `rendering` → `sent_for_review`, файл в `data/rendered/`

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
2026-11-25 · CR-001 · agent(scaffold) · по ревью каркаса выпущено ТЗ на правки docs/CHANGES-v1.2.md: 5 новых задач (S0-04, S1-08, S2-05, S3-09, S3-10), правки SPEC до v1.2, ADR D-012…D-016, LICENSE/.editorconfig/PR-шаблон · CR не применён, код не начат · следующий шаг: исполнить CR-001, затем S1-01
```
