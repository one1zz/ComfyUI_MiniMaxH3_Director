"""Lightweight wiring guards for the P0/P1 fixes.

These read source text instead of executing the executor (which needs ComfyUI),
to pin the two audit regressions without a GPU.
"""

from __future__ import annotations

import pathlib

_EXEC = pathlib.Path(__file__).resolve().parent.parent / "director" / "executor_core.py"
_PACK = pathlib.Path(__file__).resolve().parent.parent / "director" / "motion_pack.py"


def test_audio_expand_uses_motion_pin_window():
    exec_src = _EXEC.read_text(encoding="utf-8")
    pack_src = _PACK.read_text(encoding="utf-8")
    # The executor delegates the decision and uses its slowed_frames (== pin window).
    assert "decide_pin_audio(" in exec_src
    assert "slowed_frames=int(_audio.slowed_frames)" in exec_src
    # The old bug expanded audio for the preferred context instead of the window.
    assert "slowed_frames=snap_context_frames(" not in exec_src
    assert "slowed_frames=snap_context_frames(" not in pack_src


def test_slowed_slowed_audio_requires_matching_dilate():
    pack_src = _PACK.read_text(encoding="utf-8")
    assert "prev_d == d" in pack_src
    assert "上一段倍率 {prev_d} ≠ " in pack_src


def test_continue_refine_lock_is_passed_for_motion():
    src = _EXEC.read_text(encoding="utf-8")
    assert "motion_keep_prefix_lock=bool(" in src


def test_executor_uses_pure_pin_decisions():
    src = _EXEC.read_text(encoding="utf-8")
    assert "select_pin_window(" in src
    assert "decide_pin_audio(" in src
    # The inline window policy must not be duplicated in the executor.
    assert "pin_window_for_available(" not in src


def test_capability_matrix_is_single_source():
    src = _PACK.read_text(encoding="utf-8")
    assert "def motion_capabilities(" in src
    assert "def motion_capability_messages(" in src
    # SelfLift must remain an explicit degradation, not a silent drop.
    assert 'CAP_DEGRADED,\n                "selflift"' in src
