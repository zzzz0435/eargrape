import pytest

from eargrape_core import (
    ConfigError,
    EffectProfile,
    config_from_dict,
    config_to_dict,
    create_default_config,
    validate_profile,
)


def _profile(**overrides):
    base = dict(
        name="x",
        distortion_mode="soft_clip",
        drive=1.0,
        mic_gain=1.0,
        post_gain=1.0,
        mix=0.0,
        noise_gate=0.0,
    )
    base.update(overrides)
    return EffectProfile(**base)


def test_validate_profile_accepts_valid():
    validate_profile(_profile())  # 不應 raise


def test_validate_profile_rejects_bad_mix():
    with pytest.raises(ConfigError):
        validate_profile(_profile(mix=1.5))


def test_validate_profile_rejects_unknown_mode():
    with pytest.raises(ConfigError):
        validate_profile(_profile(distortion_mode="fuzz"))


def test_validate_profile_rejects_empty_name():
    with pytest.raises(ConfigError):
        validate_profile(_profile(name="  "))


def test_default_config_has_two_profiles():
    config = create_default_config()
    assert config.profile_a.name == "普通"
    assert config.profile_a.drive == 1.0
    assert config.profile_a.mix == 0.0
    assert config.profile_b.name == "爆麥"
    assert config.profile_b.drive == 18.0
    assert config.start_pressed is False


def test_migration_from_legacy_flat_config():
    legacy = {
        "hotkey": "f8",
        "start_enabled": True,
        "distortion_mode": "hard_clip",
        "drive": 20.0,
        "mic_gain": 3.0,
        "post_gain": 0.4,
        "mix": 1.0,
        "noise_gate": 0.01,
    }
    config = config_from_dict(legacy)
    assert config.start_pressed is True
    assert config.profile_b.distortion_mode == "hard_clip"
    assert config.profile_b.drive == 20.0
    assert config.profile_b.mic_gain == 3.0
    assert config.profile_b.post_gain == 0.4
    assert config.profile_a.drive == 1.0
    assert config.profile_a.mix == 0.0
    assert config.profile_a.mic_gain == 3.0  # 沿用舊 boost


def test_migration_missing_mic_gain_defaults_to_one():
    legacy = {"hotkey": "f8", "drive": 18.0, "post_gain": 0.32, "mix": 1.0}
    config = config_from_dict(legacy)
    assert config.profile_a.mic_gain == 1.0
    assert config.profile_b.mic_gain == 1.0


def test_new_format_roundtrip():
    config = create_default_config()
    data = config_to_dict(config)
    again = config_from_dict(data)
    assert config_to_dict(again) == data
