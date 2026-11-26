from pathlib import Path

import pytest
from pydantic import ValidationError

from shorteditor.core.config import AppConfig, ConfigManager, load_config, load_settings


def test_missing_required_environment_key_is_clear(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ADMIN_ID",
        "TWITCH_CLIENT_ID",
        "TWITCH_CLIENT_SECRET",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError) as exc:
        load_settings(tmp_path / "missing.env")

    assert "telegram_bot_token" in str(exc.value)


def test_environment_settings_load_required_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    values = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_ADMIN_ID": "123",
        "TWITCH_CLIENT_ID": "client-id",
        "TWITCH_CLIENT_SECRET": "client-secret",
        "R2_ACCOUNT_ID": "account",
        "R2_ACCESS_KEY_ID": "access",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET": "bucket",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = load_settings(tmp_path / "missing.env")

    assert settings.telegram_admin_id == 123
    assert settings.r2_bucket == "bucket"


def test_config_defaults_match_example_values() -> None:
    config = AppConfig.model_validate({})
    example = load_config("config.example.yaml")

    assert config.parser.poll_interval_minutes == 15
    assert config.parser.max_duration_seconds == 60
    assert config.parser.candidate_ttl_hours == 24
    assert config.queue.max_concurrent_renders == 1
    assert config.queue.claim_ttl_minutes == 15
    assert config.transcribe.model == "medium"
    assert config.transcribe.llm_normalize.enabled is False
    assert config.subtitles.font_size == 68
    assert config.subtitles.margin_v_percent == 60
    assert config.render.fit == "contain"
    assert config.render.fps == "auto"
    assert config.publish.retention_days == 180
    assert config.render.max_size_mb == 45
    assert config.render.crf_step == 4
    assert config.render.max_size_retries == 2

    assert example == config


def test_invalid_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("parser:\n  max_duration_seconds: nope\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(path)


def test_config_reload_applies_parser_changes(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("parser:\n  min_views: 100\n", encoding="utf-8")
    manager = ConfigManager(config_path=path)

    first = manager.reload()
    path.write_text("parser:\n  min_views: 500\n", encoding="utf-8")
    second = manager.reload()

    assert first.parser.min_views == 100
    assert second.parser.min_views == 500


@pytest.mark.parametrize("fps", ["auto", 60])
def test_render_fps_accepts_auto_and_valid_integer(fps: str | int) -> None:
    config = AppConfig.model_validate({"render": {"fps": fps}})

    assert config.render.fps == fps


def test_render_fps_rejects_120() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"render": {"fps": 120}})


@pytest.mark.parametrize("ttl", [0, 169])
def test_candidate_ttl_rejects_out_of_range(ttl: int) -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"parser": {"candidate_ttl_hours": ttl}})


def test_queue_claim_ttl_rejects_values_below_one() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"queue": {"claim_ttl_minutes": 0}})


def test_llm_normalize_defaults_to_disabled() -> None:
    config = AppConfig.model_validate({})

    assert config.transcribe.llm_normalize.enabled is False


def test_unknown_config_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"parser": {"unknown_key": True}})
