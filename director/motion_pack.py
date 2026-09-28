"""External Motion Fix pack for MiniMax H3 Director (graph-wired config).

Connect ``MiniMaxH3DirectorMotionFix.motion_fix`` → ``MiniMaxH3Director.motion_fix``.
Unconnected = current single-pass sampling. The pack carries node-level defaults;
per-segment on/off and dilation come from the timeline rows
(``motionFix`` / ``motionDilate``) in both global and segment edit modes.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    TRAINED_MAX_SLOWED_FRAMES,
    dilation_pin_window,
    dilation_supports_continuity,
    pin_window_for_available,
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


CAP_OK = "ok"
CAP_HINT = "hint"
CAP_DEGRADED = "degraded"
CAP_UNSUPPORTED = "unsupported"

_VALID_CAP_LEVELS = (CAP_OK, CAP_HINT, CAP_DEGRADED, CAP_UNSUPPORTED)


@dataclass(frozen=True)
class MotionCapability:
    """One resolved capability/conflict note for a motion-enabled segment.

    Single source of truth: the executor's run report, node tooltips and the
    docs all read these instead of re-deriving the rules per call site.
    """

    level: str
    code: str
    message: str = ""


def _cap(level: str, code: str, message: str = "") -> MotionCapability:
    if level not in _VALID_CAP_LEVELS:
        raise ValueError(f"capability level must be one of {_VALID_CAP_LEVELS}")
    return MotionCapability(level=level, code=code, message=message)


def motion_capabilities(
    *,
    task_key: str = "",
    enabled: bool = False,
    dilate: int = DEFAULT_DILATE,
    slowed_frames: int = 0,
    max_slowed_frames: int = DEFAULT_MAX_SLOWED_FRAMES,
    context_frames: int = 22,
    continuity: str = "off",
    audio_mode: str = "generate",
    exact_export: bool = False,
    refine: str = "off",
    selflift: bool = False,
    face_refine: bool = False,
    semantic_bridge: bool = False,
    fps: float = 24.0,
) -> tuple[MotionCapability, ...]:
    """Resolve all capability/conflict notes for one motion-enabled segment.

    Pure: no torch, no ComfyUI. ``continuity`` is off|guide|continue,
    ``audio_mode`` is generate|source|mute, ``refine`` is off|refine|upscale.
    Every conflict the feature knows about must appear here with a hint or a
    degradation note, so no call site silently drops a combination.
    """
    task = str(task_key or "").strip().lower()
    d = max(1, int(dilate or DEFAULT_DILATE))
    slowed = max(0, int(slowed_frames or 0))
    max_slowed = max(5, int(max_slowed_frames or DEFAULT_MAX_SLOWED_FRAMES))
    ctx = max(1, int(context_frames or 22))
    cont = str(continuity or "off").strip().lower()
    audio = str(audio_mode or "generate").strip().lower()
    ref = str(refine or "off").strip().lower()
    caps: list[MotionCapability] = []

    if not enabled:
        return (_cap(CAP_OK, "motion_off", "动作修复未开启"),)
    if task not in MOTION_TASK_KEYS:
        return (
            _cap(
                CAP_UNSUPPORTED,
                "task",
                f"动作修复仅支持 v2v / rv2v，当前任务 {task or '未知'} 已跳过",
            ),
        )
    if float(fps or 24.0) != 24.0:
        caps.append(
            _cap(CAP_HINT, "fps", "动作修复的音频时基按 24fps 设计，当前帧率非 24")
        )
    if selflift:
        caps.append(
            _cap(
                CAP_DEGRADED,
                "selflift",
                "动作修复与 SelfLift 暂不支持叠加，本段已跳过动作修复（二选一）",
            )
        )
    if cont == "continue" and ref == "refine":
        caps.append(
            _cap(
                CAP_OK,
                "continue_refine",
                "引导+重绘 与同尺寸二采叠加：保留前缀硬锁",
            )
        )
    elif cont == "continue" and ref == "upscale":
        caps.append(
            _cap(
                CAP_HINT,
                "continue_refine",
                "引导+重绘 与放大二采叠加：放大后前缀硬锁不再保留"
                "（前缀仍会随后裁掉），接缝由钉入帧维持",
            )
        )
    if audio == "source" and cont != "off" and not exact_export:
        caps.append(
            _cap(
                CAP_HINT,
                "source_exact",
                "原声 + 段间引导：将自动启用精确导出以避免源声漂移",
            )
        )
    if slowed > TRAINED_MAX_SLOWED_FRAMES:
        caps.append(
            _cap(
                CAP_HINT,
                "trained_range",
                f"放慢总长 {slowed}f 超出 H3 训练区间（约 124–{TRAINED_MAX_SLOWED_FRAMES}f），"
                "画质/显存/耗时未验证",
            )
        )
    if slowed > max_slowed:
        caps.append(
            _cap(
                CAP_HINT,
                "soft_limit",
                f"放慢总长 {slowed}f 超过设定上限 {max_slowed}f（软限，可继续但风险自负）",
            )
        )
    if d == 1:
        caps.append(_cap(CAP_HINT, "noop", "倍率=1：动作修复不改变帧数（等同于关闭）"))
    window = dilation_pin_window(d)
    if window is None:
        caps.append(
            _cap(
                CAP_HINT,
                "no_window",
                f"倍率 {d} 不整除任何合法衔接窗口（5/22/39/56），该段边界按硬切处理",
            )
        )
    elif ctx % d != 0 and ref != "off":
        caps.append(
            _cap(
                CAP_HINT,
                "window_promotion",
                f"当前上下文 {ctx}f 不能被倍率 {d} 整除，钉入窗口将取 {window}f 以对齐链路",
            )
        )
    if semantic_bridge:
        caps.append(
            _cap(
                CAP_HINT,
                "semantic_bridge",
                "Semantic Bridge 与动作修复为兼容性组合（非蒸馏任务），未充分验证，可关闭作 A/B",
            )
        )
    if face_refine:
        caps.append(
            _cap(CAP_OK, "face_refine", "动作修复在恢复实时帧后进行修脸，组合安全")
        )
    if not caps:
        caps.append(_cap(CAP_OK, "ok", ""))
    return tuple(caps)


def motion_capability_messages(
    caps,
    *,
    levels: tuple[str, ...] = (CAP_DEGRADED, CAP_UNSUPPORTED, CAP_HINT),
) -> list[str]:
    """Human messages for the run report (default: everything actionable)."""
    out: list[str] = []
    for cap in caps or ():
        if cap.level in levels and cap.message:
            out.append(cap.message)
    return out


def motion_meta_usable(meta) -> bool:
    """True when a stored per-segment motion handoff can drive a slowed pin.

    A handoff written by another run may be truncated/corrupt; its slowed trim
    coordinates are meaningless without the hold map and dilation, so callers
    must hard-cut rather than reinterpret them on the real clock.
    """
    if not isinstance(meta, dict):
        return False
    return (
        int(meta.get("real_frames") or 0) > 0
        and int(meta.get("dilate") or 0) > 0
        and bool(meta.get("hold_map"))
    )


@dataclass(frozen=True)
class PinWindowDecision:
    """Resolved slowed pin window for a motion segment seam."""

    window: int | None
    preferred: int
    planned: int
    dilate: int
    promoted: bool = False

    @property
    def real_frames(self) -> int:
        if not self.window:
            return 0
        return int(self.window) // max(1, int(self.dilate))


def select_pin_window(
    *, preferred: int, dilate: int, available_slowed: int, planned: int
) -> PinWindowDecision:
    """Pick a legal slowed pin window (5/22/39/56, divisible by dilate).

    Single source of truth for the seam-window policy: use the user's context
    when it fits the slowed budget, otherwise the largest legal window that does
    (capped by the dilation's own legal window). Pure integer logic.
    """
    d = max(1, int(dilate or 1))
    pref = max(0, int(preferred or 0))
    avail = max(0, int(available_slowed or 0))
    plan = max(0, int(planned or 0))
    window: int | None = None
    if pref % d == 0 and pref <= avail:
        window = pref
    if window is None and plan:
        window = pin_window_for_available(avail, d, min_real=1)
        if window:
            window = min(int(window), plan)
    return PinWindowDecision(
        window=int(window) if window else None,
        preferred=pref,
        planned=plan,
        dilate=d,
        promoted=bool(window) and int(window) != pref,
    )


@dataclass(frozen=True)
class PinAudioDecision:
    """Where the next segment's pinned audio comes from.

    ``latent``: slice the previous slowed AV latent (same dilation).
    ``expand``: repeat the previous real-time audio tail x dilate.
    ``none``: no usable previous audio; pin video only.
    """

    source: str
    slowed_frames: int
    prev_dilate: int
    dilate: int
    note: str = ""


def decide_pin_audio(
    *,
    prev_motion_meta,
    has_prev_av: bool,
    has_prev_audio: bool,
    dilate: int,
    pin_window: int,
) -> PinAudioDecision:
    """Resolve the audio pin source and its slowed length.

    The expanded/sliced audio must always cover ``pin_window`` slowed frames —
    the same window the video pin uses. A different previous dilation cannot be
    sliced (its slowed clock differs), so it degrades to a real-time xd expand.
    """
    d = max(1, int(dilate or 1))
    window = max(0, int(pin_window or 0))
    prev_d = (
        int((prev_motion_meta or {}).get("dilate") or 0) if prev_motion_meta else 0
    )
    if prev_motion_meta and prev_d == d and has_prev_av:
        return PinAudioDecision(
            "latent",
            window,
            prev_d,
            d,
            f"音频钉入上一段放慢 latent（{window}f slowed）",
        )
    if not has_prev_audio:
        return PinAudioDecision(
            "none",
            window,
            prev_d,
            d,
            "无可展开的上一段音频，音频不钉入（视频照常钉入）",
        )
    note = ""
    if prev_motion_meta and prev_d != d:
        note = f"上一段倍率 {prev_d} ≠ 本段 {d}，音频改用实时展开以避免时基错位"
    return PinAudioDecision("expand", window, prev_d, d, note)



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
    "MotionCapability",
    "CAP_OK",
    "CAP_HINT",
    "CAP_DEGRADED",
    "CAP_UNSUPPORTED",
    "motion_capabilities",
    "motion_capability_messages",
    "motion_meta_usable",
    "PinWindowDecision",
    "PinAudioDecision",
    "select_pin_window",
    "decide_pin_audio",
]
