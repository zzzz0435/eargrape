import numpy as np

from eargrape_core import (
    EargrapeRouter,
    config_from_dict,
    config_to_dict,
    create_default_config,
)


def _make_router(blocksize, start_pressed=False):
    data = config_to_dict(create_default_config())
    data["blocksize"] = blocksize
    data["start_pressed"] = start_pressed
    return EargrapeRouter(config_from_dict(data))


def _run_block(router, samples):
    indata = np.asarray(samples, dtype=np.float32).reshape(-1, 1)
    outdata = np.zeros_like(indata)
    router.callback(indata, outdata, indata.shape[0], None, 0)
    return outdata[:, 0]


def test_profile_a_is_clean_passthrough():
    router = _make_router(blocksize=3)
    out = _run_block(router, [0.1, -0.2, 0.3])
    np.testing.assert_allclose(out, [0.1, -0.2, 0.3], atol=1e-6)


def test_toggle_switches_to_b_distortion():
    router = _make_router(blocksize=2)
    assert router.toggle() is True
    out = _run_block(router, [0.5, -0.5])
    assert not np.allclose(out, [0.5, -0.5])
    assert np.all(np.abs(out) <= 1.0)


def test_active_profile_name_follows_toggle():
    router = _make_router(blocksize=2)
    assert router.active_profile_name() == "普通"
    router.toggle()
    assert router.active_profile_name() == "爆麥"


def test_start_pressed_starts_on_b():
    router = _make_router(blocksize=2, start_pressed=True)
    assert router.is_b_active() is True
    assert router.active_profile_name() == "爆麥"
