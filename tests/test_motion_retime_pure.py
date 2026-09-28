"""Pure integer/window math in ``director.motion_retime``.

These tests need no torch tensors, so they run everywhere.
"""

from __future__ import annotations

import pytest

from director import motion_retime as mr


def test_supported_dilations_divides_legal_windows():
    assert mr.supported_dilations() == (1, 2, 3, 4, 7, 8)
    for d in mr.supported_dilations():
        window = mr.dilation_pin_window(d)
        assert window in mr.LEGAL_PIN_WINDOWS
        assert window % d == 0
        assert window // d >= 5


def test_dilation_pin_window_picks_largest_legal():
    assert mr.dilation_pin_window(1) == 56
    assert mr.dilation_pin_window(2) == 56
    assert mr.dilation_pin_window(3) == 39
    assert mr.dilation_pin_window(4) == 56
    assert mr.dilation_pin_window(7) == 56
    assert mr.dilation_pin_window(8) == 56
    # No legal window divisible with a useful real overlap.
    for d in (5, 6, 9, 13):
        assert mr.dilation_pin_window(d) is None


def test_pin_window_for_available_respects_budget():
    # window must fit available slowed frames, divide d, and keep min real.
    assert mr.pin_window_for_available(56, 2, min_real=1) == 56
    assert mr.pin_window_for_available(40, 2, min_real=1) == 22
    # d=2: the smallest legal window is 22 (5 is odd), so <22 has no window.
    assert mr.pin_window_for_available(21, 2, min_real=1) is None
    assert mr.pin_window_for_available(4, 2, min_real=1) is None
    # d=3 only 39 divides among the legal windows.
    assert mr.pin_window_for_available(100, 3, min_real=1) == 39
    assert mr.pin_window_for_available(38, 3, min_real=1) is None


def test_uniform_hold_map_and_total():
    holds = mr.build_uniform_hold_map(7, 3)
    assert holds == [3] * 7
    assert mr.hold_map_total(holds) == 21
    assert mr.hold_map_total([]) == 0


def test_align_windows_match_official_grid():
    from director.frame_align import minimax_align_frame_count

    for n, want in ((124, 124), (125, 141), (260, 260), (316, 328), (5, 5)):
        assert minimax_align_frame_count(n) == want


def test_plan_length_audit_offsets():
    text = mr.plan_length_audit([(0, 124, 124), (1, 124, 136)])
    assert "#1: 124f → 124f (+0f, cum +0f)" in text
    assert "#2: 124f → 136f (+12f, cum +12f)" in text


def test_soft_limit_constants_are_ordered():
    assert mr.TRAINED_MAX_SLOWED_FRAMES == 362
    assert mr.DEFAULT_MAX_SLOWED_FRAMES == 512
    assert mr.HARD_MAX_SLOWED_FRAMES == 3600
    assert mr.TRAINED_MAX_SLOWED_FRAMES < mr.DEFAULT_MAX_SLOWED_FRAMES


@pytest.mark.parametrize("d,real,expected", [(1, 124, 124), (2, 124, 260), (3, 90, 277)])
def test_align_of_hold_total(d, real, expected):
    total = real * d
    from director.frame_align import minimax_align_frame_count

    assert minimax_align_frame_count(total) == expected
