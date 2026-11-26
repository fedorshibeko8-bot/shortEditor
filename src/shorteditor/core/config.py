from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(min_length=1)
    telegram_admin_id: int
    twitch_client_id: str = Field(min_length=1)
    twitch_client_secret: str = Field(min_length=1)
    r2_account_id: str = Field(min_length=1)
    r2_access_key_id: str = Field(min_length=1)
    r2_secret_access_key: str = Field(min_length=1)
    r2_bucket: str = Field(min_length=1)
    r2_public_base_url: str | None = None
    log_level: str = "INFO"
    tz: str = "Europe/Moscow"


class ParserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_minutes: int = 15
    lookback_hours: int = 24
    max_duration_seconds: int = 60
    min_duration_seconds: int = 5
    min_views: int = 100
    max_views: int | None = None
    categories: list[str] = Field(default_factory=list)
    channels_whitelist: list[str] = Field(default_factory=list)
    channels_blacklist: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    max_candidates_per_poll: int = 20
    candidate_ttl_hours: int = Field(default=24, ge=1, le=168)
    candidate_ttl_scan_minutes: int = Field(default=10, ge=1)


class QueueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_pending_candidates: int = 50
    max_concurrent_renders: int = 1
    max_attempts: int = 3
    claim_ttl_minutes: int = Field(default=15, ge=1)
    poll_interval_seconds: int = Field(default=5, ge=1)


class LlmNormalizeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class TranscribeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "faster-whisper"
    model: str = "medium"
    fallback_model: str = "large-v3"
    language: str = "ru"
    word_timestamps: bool = True
    initial_prompt: str = ""
    glossary: dict[str, str] = Field(default_factory=dict)
    llm_normalize: LlmNormalizeConfig = Field(default_factory=lambda: LlmNormalizeConfig())


class SubtitleHookConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    text: str = ""
    font_size: int = 56
    position_y_percent: int = 12


class SubtitlesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = "ass"
    mode: str = "karaoke"
    font_family: str = "Montserrat ExtraBold"
    font_fallback: str = "Inter Black"
    font_size: int = 68
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00000000"
    outline_px: int = 5
    shadow_px: int = 0
    margin_v_percent: int = 60
    max_chars_per_line: int = 25
    max_words_per_line: int = 6
    max_lines: int = 2
    uppercase: bool = False
    hook: SubtitleHookConfig = Field(default_factory=SubtitleHookConfig)


class BackgroundBlurConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mode: str = "gblur"
    sigma: int = 20


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = 1080
    height: int = 1920
    fps: Literal["auto"] | int = "auto"
    video_codec: str = "libx264"
    preset: str = "medium"
    crf: int = 20
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    background_blur: BackgroundBlurConfig = Field(default_factory=BackgroundBlurConfig)
    fit: str = "contain"
    max_size_mb: int = 45
    crf_step: int = 4
    max_size_retries: int = 2

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, value: Literal["auto"] | int) -> Literal["auto"] | int:
        if value != "auto" and not 1 <= value <= 60:
            raise ValueError("fps must be 'auto' or an integer from 1 to 60")
        return value


class PublishConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "r2"
    key_template: str = "{yyyy}/{mm}/{dd}/{clip_id}.mp4"
    meta_template: str = "{yyyy}/{mm}/{dd}/{clip_id}.meta.json"
    cleanup_temp_after_publish: bool = True
    cleanup_temp_after_reject: bool = True
    retention_days: int = Field(default=180, ge=1)


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_digest_at: str = "21:00"
    disk_free_alert_percent: int = 10
    disk_check_minutes: int = Field(default=10, ge=1)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    dir: str = "logs"
    rotation_mb: int = 50
    backups: int = 5


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser: ParserConfig = Field(default_factory=ParserConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    subtitles: SubtitlesConfig = Field(default_factory=SubtitlesConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class ConfigManager:
    def __init__(self, config_path: str | Path = "config.yaml", env_file: str | Path = ".env") -> None:
        self.config_path = Path(config_path)
        self.env_file = Path(env_file)
        self._lock = RLock()
        self._settings: AppSettings | None = None
        self._config: AppConfig | None = None

    def load_settings(self) -> AppSettings:
        env_file = str(self.env_file) if self.env_file.exists() else None
        return AppSettings(_env_file=env_file)

    def load(self) -> AppConfig:
        with self._lock:
            if not self.config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            with self.config_path.open("r", encoding="utf-8") as stream:
                raw: Any = yaml.safe_load(stream) or {}
            if not isinstance(raw, dict):
                raise TypeError("Configuration root must be a mapping")
            self._config = AppConfig.model_validate(raw)
            return self._config

    def reload(self) -> AppConfig:
        return self.load()

    @property
    def settings(self) -> AppSettings:
        with self._lock:
            if self._settings is None:
                self._settings = self.load_settings()
            return self._settings

    @property
    def config(self) -> AppConfig:
        with self._lock:
            if self._config is None:
                self._config = self.load()
            return self._config


def load_settings(env_file: str | Path = ".env") -> AppSettings:
    path = Path(env_file)
    return AppSettings(_env_file=str(path) if path.exists() else None)


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        raw: Any = yaml.safe_load(stream) or {}
    if not isinstance(raw, dict):
        raise TypeError("Configuration root must be a mapping")
    return AppConfig.model_validate(raw)
