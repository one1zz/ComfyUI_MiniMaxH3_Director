"""Pin-window reporting: phase-align is a prediction; the pixel path reports its real tail."""

from __future__ import annotations

import logging

from director.h3_motion_context import (
    _phase_aligned_tail_start,
    describe_pixel_pin_window,
)

LOGGER = "ComfyUI-MiniMaxH3-Director.h3_motion_context"


class _FakeTail:
    """Only needs ``.shape`` — enough for the report helper without torch."""

    def __init__(self, n: int):
        self.shape = (n,)


def test_phase_align_prediction_is_silent(caplog):
    # 42 tokens == 141px clip; a 7-step (22f) window ends at 141, gap to 157.
    with caplog.at_level(logging.INFO, logger=LOGGER):
        start, pin_end, gap = _phase_aligned_tail_start(
            42, 7, 157, announce=False
        )
    assert (start, pin_end, gap) == (35, 141, 16)
    assert "will be trimmed" not in caplog.text


def test_phase_align_actual_pin_announces_trim(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        _phase_aligned_tail_start(42, 7, 157, announce=True)
    assert "will be trimmed" in caplog.text


def test_pixel_pin_reports_real_prev_export_tail():
    note = describe_pixel_pin_window(_FakeTail(157), 22)
    # Real last frames of the export, which may be off the 17k+5 grid.
    assert "[135:157)" in note
    assert "no prev-export trim" in note


def test_pixel_pin_clamps_to_available_frames():
    note = describe_pixel_pin_window(_FakeTail(10), 22)
    assert "[0:10)" in note


def test_pixel_pin_handles_missing_tail():
    assert describe_pixel_pin_window(None, 22) == ""
    assert describe_pixel_pin_window(_FakeTail(0), 22) == ""
