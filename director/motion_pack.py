"""External Motion Fix pack for MiniMax H3 Director (graph-wired config).

Connect ``MiniMaxH3DirectorMotionFix.motion_fix`` → ``MiniMaxH3Director.motion_fix``.
Unconnected = current single-pass sampling. The pack carries node-level defaults;
per-segment on/off and dilation come from the timeline rows
(``motionFix`` / ``motionDilate``) in both global and segment edit modes.
"""

from __future__ import annotations

from typing import Any

from .motion_retime import (
    AUDIO_RECOVER_MODES,
    DEFAULT_AUDIO_RECOVER,
    DEFAULT_BRIDGE_FRAMES,
    DEFAULT_DILATE,
    DEFAULT_GATE_ABS,
    DEFAULT_GATE_REL,
    DEFAULT_MAX_SLOWED_FRAMES,
    DEFAULT_MIN_MOTION_FRAMES,
    DEFAULT_RAMP_FRAMES,
    MAX_DILATE,
    MOTION_MODES,
    MOTION_PIPELINE_ID,
    build_uniform_hold_map,
    dilation_pin_window,
    dilation_supports_continuity,
    hold_map_total,
    supported_dilations,
)

MMX_DIR_MOTION = "MMX_DIR_MOTION"

MOTION_TASK_KEYS = frozenset({"v2v", "rv2v"})

DEFAULT_SOURCE_INIT_DENOISE = 0.60
MAX_SOURCE_INIT_DENOISE = 0.95


def _clamp_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = int(default)
    return max(lo, min(hi, n))


def _clamp_float(raw: Any, default: float, lo: float, hi: float) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = float(default)
    return max(lo, min(hi, v))


def clamp_dilate(raw: Any) -> int:
    return _clamp_int(raw, DEFAULT_DILATE, 1, MAX_DILATE)


def _clamp_audio_recover(raw: Any) -> str:
    mode = str(raw or DEFAULT_AUDIO_RECOVER).strip().lower()
    return mode if mode in AUDIO_RECOVER_MODES else DEFAULT_AUDIO_RECOVER


def pack_motion(
    *,
    mode: str = "uniform",
    dilate: int = DEFAULT_DILATE,
    source_init_denoise: float = DEFAULT_SOURCE_INIT_DENOISE,
    audio_recover: str = DEFAULT_AUDIO_RECOVER,
    gate_abs: float = DEFAULT_GATE_ABS,
    gate_rel: float = DEFAULT_GATE_REL,
    bridge: int = DEFAULT_BRIDGE_FRAMES,
    ramp: int = DEFAULT_RAMP_FRAMES,
    min_frames: int = DEFAULT_MIN_MOTION_FRAMES,
    max_slowed_frames: int = DEFAULT_MAX_SLOWED_FRAMES,
    fail_fallback: bool = True,
) -> dict[str, Any]:
    mode = str(mode or "uniform").strip().lower()
    if mode not in MOTION_MODES:
        mode = "uniform"
    return {
        "enabled": True,
        "mode": mode,
        "dilate": clamp_dilate(dilate),
        "source_init_denoise": _clamp_float(
            source_init_denoise, DEFAULT_SOURCE_INIT_DENOISE, 0.0, MAX_SOURCE_INIT_DENOISE
        ),
        "audio_recover": _clamp_audio_recover(audio_recover),
        "gate_abs": _clamp_float(gate_abs, DEFAULT_GATE_ABS, 0.0, 100.0),
        "gate_rel": _clamp_float(gate_rel, DEFAULT_GATE_REL, 0.0, 1.0),
        "bridge": _clamp_int(bridge, DEFAULT_BRIDGE_FRAMES, 0, 20),
        "ramp": _clamp_int(ramp, DEFAULT_RAMP_FRAMES, 0, 20),
        "min_frames": _clamp_int(min_frames, DEFAULT_MIN_MOTION_FRAMES, 5, 512),
        "max_slowed_frames": _clamp_int(
            max_slowed_frames, DEFAULT_MAX_SLOWED_FRAMES, 5, 3600
        ),
        "fail_fallback": bool(fail_fallback),
        "pipeline": MOTION_PIPELINE_ID,
    }


def normalize_motion_pack(raw) -> dict[str, Any] | None:
    """Director execute: None if unconnected / invalid / disabled."""
    if not isinstance(raw, dict):
        return None
    if raw.get("enabled") is False:
        return None
    mode = str(raw.get("mode") or "uniform").strip().lower()
    if mode not in MOTION_MODES:
        mode = "uniform"
    return {
        "enabled": True,
        "mode": mode,
        "dilate": clamp_dilate(raw.get("dilate")),
        "source_init_denoise": _clamp_float(
            raw.get("source_init_denoise"),
            DEFAULT_SOURCE_INIT_DENOISE,
            0.0,
            MAX_SOURCE_INIT_DENOISE,
        ),
        "audio_recover": _clamp_audio_recover(raw.get("audio_recover")),
        "gate_abs": _clamp_float(raw.get("gate_abs"), DEFAULT_GATE_ABS, 0.0, 100.0),
        "gate_rel": _clamp_float(raw.get("gate_rel"), DEFAULT_GATE_REL, 0.0, 1.0),
        "bridge": _clamp_int(raw.get("bridge"), DEFAULT_BRIDGE_FRAMES, 0, 20),
        "ramp": _clamp_int(raw.get("ramp"), DEFAULT_RAMP_FRAMES, 0, 20),
        "min_frames": _clamp_int(
            raw.get("min_frames"), DEFAULT_MIN_MOTION_FRAMES, 5, 512
        ),
        "max_slowed_frames": _clamp_int(
            raw.get("max_slowed_frames"), DEFAULT_MAX_SLOWED_FRAMES, 5, 3600
        ),
        "fail_fallback": bool(raw.get("fail_fallback", True)),
        "pipeline": str(raw.get("pipeline") or MOTION_PIPELINE_ID),
    }


def motion_master(plan) -> dict[str, Any] | None:
    pack = getattr(plan, "motion_fix", None)
    if not isinstance(pack, dict) or not pack.get("enabled"):
        return None
    return pack


def motion_enabled_for_segment(plan, seg) -> bool:
    master = motion_master(plan)
    if master is None or seg is None:
        return False
    if str(getattr(seg, "task_key", "") or "") not in MOTION_TASK_KEYS:
        return False
    return bool(getattr(seg, "motion_fix_enabled", False))


def resolve_motion_for_segment(plan, seg) -> dict[str, Any] | None:
    """Merge node defaults with the segment's on/off + dilation override."""
    master = motion_master(plan)
    if master is None or not motion_enabled_for_segment(plan, seg):
        return None
    out = dict(master)
    override = int(getattr(seg, "motion_dilate", 0) or 0)
    if override > 0:
        out["dilate"] = clamp_dilate(override)
    out["ack"] = (
        f"seg#{int(getattr(seg, 'index', 0)) + 1} "
        f"dilate={out['dilate']} mode={out['mode']}"
    )
    return out


def motion_fingerprint(plan, seg) -> dict[str, Any]:
    """Only emitted for segments with motion enabled — other caches stay valid."""
    cfg = resolve_motion_for_segment(plan, seg)
    if cfg is None:
        return {}
    return {
        "motion": True,
        "motion_pipeline": cfg.get("pipeline") or MOTION_PIPELINE_ID,
        "motion_mode": cfg.get("mode") or "uniform",
        "motion_dilate": int(cfg.get("dilate") or 1),
        "motion_init_denoise": round(float(cfg.get("source_init_denoise") or 0.0), 4),
        "motion_audio_recover": str(cfg.get("audio_recover") or DEFAULT_AUDIO_RECOVER),
        "motion_gate_abs": round(float(cfg.get("gate_abs") or 0.0), 4),
        "motion_gate_rel": round(float(cfg.get("gate_rel") or 0.0), 4),
        "motion_bridge": int(cfg.get("bridge") or 0),
        "motion_ramp": int(cfg.get("ramp") or 0),
        "motion_min_frames": int(cfg.get("min_frames") or 0),
        "motion_max_slowed": int(cfg.get("max_slowed_frames") or 0),
    }


def motion_report_line(plan, seg=None) -> str | None:
    master = motion_master(plan)
    if master is None:
        return None
    if seg is None:
        d = int(master.get("dilate") or DEFAULT_DILATE)
        pin = dilation_pin_window(d)
        pin_note = (
            f"pin W={pin} (real {pin // d}f)" if pin else "no legal pin window — hard cut"
        )
        segs = [
            int(s.index) + 1
            for s in (getattr(plan, "segments", None) or [])
            if motion_enabled_for_segment(plan, s)
        ]
        return (
            f"Motion Fix: ON ({master.get('mode')}, dilate={d}, "
            f"init denoise={float(master.get('source_init_denoise') or 0.0):.2f}, "
            f"audio={master.get('audio_recover') or DEFAULT_AUDIO_RECOVER}) — "
            f"segments {segs or 'none'}; {pin_note}"
        )
    cfg = resolve_motion_for_segment(plan, seg)
    if cfg is None:
        return None
    d = int(cfg.get("dilate") or 1)
    return (
        f"Seg #{int(seg.index) + 1} motion: dilate={d}, mode={cfg.get('mode')}, "
        f"init={float(cfg.get('source_init_denoise') or 0.0):.2f}, "
        f"audio={cfg.get('audio_recover') or DEFAULT_AUDIO_RECOVER}, "
        f"window={dilation_pin_window(d) or 'hard-cut'}"
    )


def motion_uniform_slowed_frames(real_frames: int, dilate: int) -> int:
    from .motion_retime import _align

    return _align(hold_map_total(build_uniform_hold_map(real_frames, dilate)))


__all__ = [
    "MMX_DIR_MOTION",
    "MOTION_TASK_KEYS",
    "DEFAULT_SOURCE_INIT_DENOISE",
    "MAX_SOURCE_INIT_DENOISE",
    "supported_dilations",
    "dilation_pin_window",
    "dilation_supports_continuity",
    "pack_motion",
    "normalize_motion_pack",
    "motion_master",
    "motion_enabled_for_segment",
    "resolve_motion_for_segment",
    "motion_fingerprint",
    "motion_report_line",
    "clamp_dilate",
]
