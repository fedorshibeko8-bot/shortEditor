# Архитектура и карта модулей

Документ описывает **целевую** раскладку кода. На этапе 0 созданы только каталоги; файлы появятся по мере выполнения задач из `docs/TASKS.md`.

## Поток данных

```
Twitch Helix ──► parser ──► SQLite (new)
                             │
                             ▼
                        bot / модерация №1
                             │ approved
                             ▼
             pipeline: download ─► extract_audio ─► transcribe
                             │                        │ words[]
                             │                        ▼
                             │                  subtitles (.ass)
                             ▼                        │
                        render (ffmpeg, один проход) ◄─┘
                             │ mp4
                             ▼
                        bot / модерация №2
                             │ publish
                             ▼
                      storage/r2 (+ meta.json) ─► published → cleanup
```

## Модули

| Путь | Ответственность | Не должен знать про |
|---|---|---|
| `src/shorteditor/core/` | Загрузка `.env`/`config.yaml`, логирование, машина статусов, планировщик, лимиты и ретраи, диск-гард | Telegram, Twitch, ffmpeg |
| `src/shorteditor/core/scheduler.py` | Планировщик джоб, advisory-lock, без внешних брокеров | Telegram, Twitch, ffmpeg |
| `src/shorteditor/parser/` | Twitch Helix клиент, применение фильтров, дедуп по `clip_id`, формирование кандидатов | Рендер, R2 |
| `src/shorteditor/bot/` | aiogram 3: middleware «только админ», хендлеры `/start`, `/status`, `/filters`, карточки и кнопки, уведомления | Прямые вызовы ffmpeg/yt-dlp |
| `src/shorteditor/bot/keyboards/` | Inline-клавиатуры модерации | Бизнес-логика |
| `src/shorteditor/bot/handlers/` | Обработка callback'ов и команд, постановка задач в БД | Тяжёлая работа в обработчике |
| `src/shorteditor/pipeline/` | Оркестрация шагов: download, audio, transcribe, subtitles, render, publish; ретраи на шаг | Telegram-разметка |
| `src/shorteditor/storage/` | SQLite (aiosqlite) репозитории и схема; R2-клиент (boto3) | Бизнес-правила модерации |
| `tests/` | unit (чистая логика: фильтры, разбивка строк, генератор .ass, статусы) и integration (конвейер с замоканными внешними API) | — |
| `docker/` | Dockerfile (python + ffmpeg + шрифты Montserrat/Inter), entrypoint | — |
| `scripts/` | Служебные скрипты: миграции, бэкап БД, ручной прогон одного клипа | — |

## Ключевые интерфейсы (контракты, не реализация)

- `transcribe(audio_path) -> list[Word]` — провайдер ASR подменяем (`faster-whisper` | `groq`).
- `normalize(words) -> words` — опциональная LLM-нормализация текста (этап 5), сохраняет число слов.
- `download(clip) -> Path`, `render(clip, words, options) -> Path`, `publish(path, meta) -> str` — шаги конвейера, каждый идемпотентен и ретраится.
- `ClipRepository` — единственный способ менять статус клипа; переходы валидируются машиной статусов.
- `validate(rendered: Path) -> None` — проверки ffprobe/SSIM.
- `fit_size(path) -> Path` — ступенчатый crf.

## Инварианты

1. Статус клипа меняется только через репозиторий и только по разрешённому переходу.
2. Скачивание — только после `approved`.
3. Таймкоды — только из ASR.
4. Исходник в кадре не кропается.
5. Параллельных рендеров не больше `queue.max_concurrent_renders` (по умолчанию 1).
6. TEMP чистится после `published`/`rejected`; при свободном месте < 10 % — алерт.
7. Файл, уходящий в Telegram, ≤ 45 МБ либо помечен как документ.
8. Кандидат без решения админа протухает по TTL и не блокирует очередь.
