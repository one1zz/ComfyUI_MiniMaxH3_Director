"""Tensor-path tests for motion retime (skipped when torch is unavailable).

Run these in the ComfyUI Python env:  python run_tests.py
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
if getattr(torch, "__mmx_test_stub__", False):
    pytest.skip(
        "real torch not available (test stub installed); run in ComfyUI Python",
        allow_module_level=True,
    )

from director import motion_retime as mr  # noqa: E402


def _clip(t: int) -> "torch.Tensor":
    return torch.arange(t, dtype=torch.float32).view(t, 1, 1, 1).repeat(1, 8, 8, 3)


def _cfg(dilate: int = 2, **over):
    cfg = {"dilate": dilate, "mode": "uniform", "audio_recover": "splice"}
    cfg.update(over)
    return cfg


def test_expand_recover_is_exact_inverse():
    clip = _clip(10)
    expanded, used = mr.expand_frames(clip, [2] * 10)
    assert expanded.shape[0] == mr.hold_map_total(used)
    back = mr.recover_held_frames(expanded, used)
    assert torch.equal(back, clip)


def test_expand_align_pad_is_recovered():
    clip = _clip(10)
    slowed_raw = mr._align(20)  # 22
    expanded, used = mr.expand_frames(clip, [2] * 10, target_frames=slowed_raw)
    assert expanded.shape[0] == slowed_raw
    assert mr.recover_held_frames(expanded, used).shape[0] == 10


def test_recover_after_slowed_trim_with_group_aligned_pin():
    clip = _clip(12)
    expanded, used = mr.expand_frames(clip, [2] * 12)  # 24 slowed
    pin = 22  # divisible by 2, on the grid
    pin_frames = torch.zeros(pin, 8, 8, 3)
    sample = torch.cat([pin_frames, expanded])
    out = mr.recover_after_slowed_trim(
        sample, used, trim_slowed=pin, dilate=2, real_frames=12
    )
    assert out.shape[0] == 12
    assert torch.equal(out, clip)


def test_build_motion_plan_reports_trained_range_and_soft_limit():
    # 124 real frames at dilate 3 -> 379 slowed (>362 trained range).
    plan = mr.build_motion_plan(_clip(124), _cfg(3), real_frames=124)
    assert plan["slowed_frames"] == 379
    assert plan["warnings"], "expected a trained-range warning"

    plan = mr.build_motion_plan(
        _clip(124), _cfg(3, max_slowed_frames=10), real_frames=124
    )
    joined = " ".join(plan["warnings"])
    assert "训练区间" in joined and "软限" in joined


def test_build_motion_plan_hard_cap_still_raises():
    with pytest.raises(ValueError):
        mr.build_motion_plan(
            _clip(124), _cfg(56, max_slowed_frames=3600), real_frames=124
        )


def test_expand_audio_window_matches_pin_window():
    audio = {"waveform": torch.zeros(1, 1, 96000), "sample_rate": 32000}
    out, slowed_n = mr.expand_audio_for_slowed_pin(
        audio, dilate=3, slowed_frames=39, fps=24
    )
    assert slowed_n == 39  # == pin window (39 % 3 == 0)
    assert out is not None
    assert out["waveform"].shape[-1] == round(39 / 24 * 32000)


def test_recover_held_audio_splice_length():
    holds = [2] * 10
    slowed_frames = sum(holds)
    wave = torch.zeros(1, 1, round(slowed_frames / 24 * 32000))
    out = mr.recover_held_audio(
        {"waveform": wave, "sample_rate": 32000},
        holds,
        trim_slowed=0,
        real_frames=10,
        fps=24,
        mode="splice",
    )
    assert out is not None
    assert out["waveform"].shape[-1] == round(10 / 24 * 32000)
