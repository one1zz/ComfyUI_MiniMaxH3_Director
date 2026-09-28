"""Cached motion first-pass frame recovery (skipped without real torch)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
if getattr(torch, "__mmx_test_stub__", False):
    pytest.skip(
        "real torch/comfy env required (test stub installed)",
        allow_module_level=True,
    )

from director.segment_cache import _trim_stale_first_pass_frames  # noqa: E402


def test_motion_pre_frames_recovered_to_real_time():
    real, d, pin = 12, 2, 22
    clip = torch.arange(real, dtype=torch.float32)
    slowed = clip.repeat_interleave(d)  # 24 slowed frames
    # Decoded sample = pinned slowed head + slowed visible.
    frames = torch.cat([torch.full((pin,), -1.0), slowed])
    handoff = {
        "motion": {
            "real_frames": real,
            "dilate": d,
            "hold_map": [d] * real,
            "slowed_trim": pin,
            "slowed_frames": len(slowed),
            "slowed_sample": int(frames.shape[0]),
        }
    }
    out = _trim_stale_first_pass_frames(
        frames, plan=None, handoff=handoff, match_len=real
    )
    assert out is not None
    assert out.shape[0] == real
    assert torch.equal(out, clip)


def test_motion_pre_frames_crop_to_match_len():
    real, d, pin = 12, 2, 22
    clip = torch.arange(real, dtype=torch.float32)
    slowed = clip.repeat_interleave(d)
    frames = torch.cat([torch.full((pin,), -1.0), slowed])
    handoff = {
        "motion": {
            "real_frames": real,
            "dilate": d,
            "hold_map": [d] * real,
            "slowed_trim": pin,
            "slowed_frames": len(slowed),
            "slowed_sample": int(frames.shape[0]),
        }
    }
    out = _trim_stale_first_pass_frames(
        frames, plan=None, handoff=handoff, match_len=8
    )
    assert out is not None and out.shape[0] == 8
    assert torch.equal(out, clip[:8])
