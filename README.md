# shortEditor

Telegram-бот автоматической нарезки и монтажа Twitch-клипов в вертикальные видео (Shorts / Reels / TikTok) с вшитыми субтитрами.

**Статус: только каркас (этап 0). Код приложения ещё не написан.**

## Что делает система

1. Круглосуточно ищет Twitch-клипы ≤ 60 сек по фильтрам (категории, каналы, просмотры, свежесть).
2. Присылает администратору карточку кандидата в Telegram → одобрение.
3. Скачивает клип, транскрибирует русскую речь (faster-whisper), генерирует `.ass`-субтитры.
4. Рендерит вертикаль 1080×1920 одним проходом ffmpeg: размытый фон + исходник целиком по центру + субтитры.
5. Отправляет готовое видео на второе одобрение → загружает мастер в Cloudflare R2.

Целевой объём: 3–5 готовых видео в день на сервере 2 vCPU / 4 GB RAM.

## Стек

Python 3.11+ · aiogram 3 · aiosqlite (SQLite) · yt-dlp · faster-whisper · ffmpeg/libass · boto3 · Docker Compose.

## Документация

| Файл | Назначение |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | Техническое задание (v1.1, с уточнениями) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Карта модулей и границы ответственности |
| [`docs/TASKS.md`](docs/TASKS.md) | Журнал задач: сделано / в работе / запланировано |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Текущее состояние проекта и точка входа для нового агента/разработчика |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Журнал архитектурных решений (ADR) |
| [`docs/CHANGES-v1.2.md`](docs/CHANGES-v1.2.md) | CR-001: ТЗ на правки документации и задач (входящее) |
| [`AGENTS.md`](AGENTS.md) | Правила работы ИИ-агентов с этим репозиторием |

## Структура

```
shortEditor/
├── AGENTS.md                  # протокол работы агентов
├── README.md
├── .env.example               # шаблон секретов (реальный .env не коммитится)
├── config.example.yaml        # шаблон настроек (фильтры, стиль, рендер)
├── docs/                      # ТЗ, архитектура, журналы
├── src/shorteditor/
│   ├── bot/                   # Telegram: хендлеры, клавиатуры, уведомления
│   ├── parser/                # Twitch Helix, фильтры, дедупликация
│   ├── pipeline/              # download → audio → transcribe → subtitles → render → publish
│   ├── storage/               # SQLite, Cloudflare R2
│   └── core/                  # конфиг, логирование, статусы, планировщик
├── tests/                     # unit / integration
├── docker/                    # Dockerfile, entrypoint
├── scripts/                   # служебные скрипты
└── data/                      # рабочие файлы (downloads/audio/rendered) — в git не попадает
```

## Порядок работы

Если вы новый участник (человек или агент) — начните с [`AGENTS.md`](AGENTS.md), затем [`docs/HANDOFF.md`](docs/HANDOFF.md).

Разработка ведётся по этапам из [`docs/TASKS.md`](docs/TASKS.md). Каждая задача имеет ID, критерии приёмки и поле «владелец»; перед завершением сессии агент обязан обновить журнал и handoff.
