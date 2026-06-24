import pytest

from eargrape_core import (
    EargrapeEngine,
    config_from_dict,
    config_to_dict,
    create_default_config,
)


def test_active_profile_name_before_start_uses_start_pressed():
    config = create_default_config()  # start_pressed False
    engine = EargrapeEngine(config)
    assert engine.active_profile_name() == "普通"

    data = config_to_dict(config)
    data["start_pressed"] = True
    engine_b = EargrapeEngine(config_from_dict(data))
    assert engine_b.active_profile_name() == "爆麥"


def test_toggle_profile_without_running_raises():
    engine = EargrapeEngine(create_default_config())
    with pytest.raises(RuntimeError):
        engine.toggle_profile()
