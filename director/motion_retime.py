"""Segment motion retiming: integer frame holds + exact recovery (Apache-2.0).

Director-owned motion fix for MiniMax H3 v2v/rv2v segments. A segment's source
clip and target timeline are slowed by integer frame holds so one H3 temporal
token no longer has to carry four distinct fast-action poses; after sampling the
held frames are dropped again (``recover``), so the exported clip keeps the
original frame count and the source soundtrack stays untouched.

Nothing here touches ComfyUI; the executor wires these helpers in.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Sequence

import torch

log = logging.getLogger("ComfyUI-MiniMaxH3-Director.director.motion_retime")

MOTION_PIPELINE_ID = "minimax_h3_director_motion_v1"

# Legal H3 pixel windows that map to whole VAE latent steps (17m+5).
LEGAL_PIN_WINDOWS = (5, 22, 39, 56)

DEFAULT_DILATE = 2
MAX_DILATE = 56
DEFAULT_MAX_SLOWED_FRAMES = 362
DEFAULT_MIN_MOTION_FRAMES = 36
DEFAULT_GATE_ABS = 2.0
DEFAULT_GATE_REL = 0.35
DEFAULT_BRIDGE_FRAMES = 2
DEFAULT_RAMP_FRAMES = 1
RECOVER_TAIL_MARGIN = 0  # extra safety: never recover fewer than this many frames

MOTION_MODES = ("uniform", "adaptive")


def _align(n: int) -> int:
    from .frame_align import minimax_align_frame_count

    return minimax_align_frame_count(max(5, int(n)))


def supported_dilations(min_real: int = 5) -> tuple[int, ...]:
    """Dilations that divide a legal pin window with a useful real overlap."""
    return tuple(
        d
        for d in range(1, MAX_DILATE + 1)
        if dilation_pin_window(d, min_real=min_real) is not None
    )


def dilation_pin_window(dilate: int, *, min_real: int = 5) -> int | None:
    """Largest legal pin window divisible by ``dilate`` (real overlap >= min_real)."""
    d = max(1, int(dilate))
    for window in reversed(LEGAL_PIN_WINDOWS):
        if window % d == 0 and window // d >= int(min_real):
            return window
    return None


def dilation_supports_continuity(dilate: int) -> bool:
    return dilation_pin_window(dilate) is not None


def pin_window_for_available(
    available_slowed: int, dilate: int, *, min_real: int = 1
) -> int | None:
    """Largest legal slowed pin window that fits the available slowed frames."""
    d = max(1, int(dilate))
    best = None
    for window in LEGAL_PIN_WINDOWS:
        if (
            window <= int(available_slowed)
            and window % d == 0
            and window // d >= int(min_real)
        ):
            best = window
    return best


def build_uniform_hold_map(n_frames: int, dilate: int) -> list[int]:
    n = max(0, int(n_frames))
    d = max(1, int(dilate))
    return [d] * n


def _frame_heat(frames: torch.Tensor, *, max_side: int = 64) -> list[float]:
    """Per-frame motion score in ~0..255 (thumbnail gray frame-to-frame MAD)."""
    if not torch.is_tensor(frames) or frames.ndim != 4 or int(frames.shape[0]) < 2:
        return []
    x = frames[..., :3].detach().float()
    t, h, w, _ = (int(x.shape[0]), int(x.shape[1]), int(x.shape[2]), int(x.shape[3]))
    if t < 2 or h < 1 or w < 1:
        return []
    import torch.nn.functional as F

    x = x.permute(0, 3, 1, 2).contiguous()
    scale = max(1.0, max(h, w) / float(max(1, max_side)))
    th = max(1, int(round(h / scale)))
    tw = max(1, int(round(w / scale)))
    if th != h or tw != w:
        x = F.interpolate(x, size=(th, tw), mode="area")
    gray = x.mean(dim=1)  # [T, h, w]
    diff = (gray[1:] - gray[:-1]).abs().mean(dim=(1, 2)) * 255.0
    heat = [float(diff[0])] + [float(v) for v in diff]  # align to frames
    # light 3-tap smoothing so single-frame noise does not open a span
    if len(heat) >= 3:
        smoothed = [heat[0]]
        for i in range(1, len(heat) - 1):
            smoothed.append((heat[i - 1] + 2.0 * heat[i] + heat[i + 1]) / 4.0)
        smoothed.append(heat[-1])
        heat = smoothed
    return heat


def motion_peak_score(frames: torch.Tensor) -> float:
    heat = _frame_heat(frames)
    return max(heat) if heat else 0.0


def build_adaptive_hold_map(
    n_frames: int,
    frames: torch.Tensor,
    *,
    dilate: int,
    gate_abs: float = DEFAULT_GATE_ABS,
    gate_rel: float = DEFAULT_GATE_REL,
    bridge: int = DEFAULT_BRIDGE_FRAMES,
    ramp: int = DEFAULT_RAMP_FRAMES,
) -> tuple[list[int], float]:
    """Hold the frames where motion is too fast; keep the rest real-time.

    Returns ``(hold_map, peak_score)``. Falls back to uniform holds when the
    heat signal is unusable, so recovery bookkeeping is always well defined.
    """
    n = max(0, int(n_frames))
    d = max(1, int(dilate))
    heat = _frame_heat(frames)
    if len(heat) != n or n < 2:
        return build_uniform_hold_map(n, d), motion_peak_score(frames)
    peak = max(heat) if heat else 0.0
    thr = max(float(gate_abs or 0.0), float(gate_rel or 0.0) * peak)
    hot = [bool(v >= thr) for v in heat]
    if not any(hot):
        return [1] * n, peak
    # bridge short valleys inside a span
    b = max(0, int(bridge))
    if b > 0:
        i = 0
        while i < n:
            if hot[i]:
                j = i + 1
                while j < n and not hot[j]:
                    j += 1
                if j < n and (j - i - 1) <= b:
                    for k in range(i + 1, j):
                        hot[k] = True
                i = j
            else:
                i += 1
    # ramp shoulders
    r = max(0, int(ramp))
    if r > 0:
        for i in range(n):
            if hot[i]:
                for k in range(max(0, i - r), i):
                    hot[k] = True
                for k in range(i + 1, min(n, i + r + 1)):
                    hot[k] = True
    hold_map = [d if hot[i] else 1 for i in range(n)]
    if all(h == 1 for h in hold_map):
        hold_map = build_uniform_hold_map(n, d)
    return hold_map, peak


def hold_map_total(hold_map: Sequence[int]) -> int:
    return int(sum(max(0, int(h)) for h in hold_map))


def expand_frames(
    clip: torch.Tensor,
    hold_map: Sequence[int],
    *,
    target_frames: int | None = None,
) -> tuple[torch.Tensor, list[int]]:
    """Repeat each source frame ``hold_map[i]`` times, extending the last group.

    ``target_frames`` is normally ``align(sum(hold_map))``; any shortfall is
    added to the final hold so the slowed clip covers the whole sample and the
    recovery map still yields exactly ``len(hold_map)`` frames.
    """
    if not torch.is_tensor(clip) or clip.ndim != 4:
        raise ValueError("motion retime: clip must be an IMAGE tensor [T,H,W,C].")
    n = int(clip.shape[0])
    holds = [max(1, int(h)) for h in hold_map]
    if len(holds) != n:
        raise ValueError(
            f"motion retime: hold map length {len(holds)} != clip frames {n}."
        )
    total = hold_map_total(holds)
    target = _align(total) if target_frames is None else max(1, int(target_frames))
    if target < total:
        raise ValueError(
            f"motion retime: target {target} shorter than held length {total}."
        )
    extra = target - total
    if extra:
        holds = list(holds)
        holds[-1] += extra
    index = torch.tensor(
        [i for i, h in enumerate(holds) for _ in range(h)],
        device=clip.device,
        dtype=torch.long,
    )
    return clip.index_select(0, index), holds


def recover_held_frames(frames: torch.Tensor, hold_map: Sequence[int]) -> torch.Tensor:
    """Keep the first frame of every hold group (exact inverse of expand_frames)."""
    if not torch.is_tensor(frames) or frames.ndim != 4:
        raise ValueError("motion retime: frames must be an IMAGE tensor [T,H,W,C].")
    n = int(frames.shape[0])
    holds = [max(1, int(h)) for h in hold_map]
    index: list[int] = []
    cursor = 0
    for h in holds:
        if cursor >= n:
            break
        index.append(min(cursor, n - 1))
        cursor += h
    if not index:
        return frames[:0]
    return frames.index_select(
        0, torch.tensor(index, device=frames.device, dtype=torch.long)
    )


def recover_after_slowed_trim(
    frames: torch.Tensor,
    hold_map: Sequence[int],
    *,
    trim_slowed: int,
    dilate: int,
    real_frames: int,
) -> torch.Tensor:
    """Trim a slowed pin head then recover group starts.

    ``trim_slowed`` must be a whole number of hold groups; callers enforce this
    via ``dilation_pin_window``. Falls back to recovering first and trimming
    real frames when the boundary is not group aligned.
    """
    trim = max(0, int(trim_slowed))
    d = max(1, int(dilate))
    real = max(0, int(real_frames))
    if trim <= 0:
        out = recover_held_frames(frames, hold_map)
        return out[:real] if real and int(out.shape[0]) > real else out
    if trim % d != 0:
        out = recover_held_frames(frames, hold_map)
        skip_real = max(0, int(round(trim / d)))
        out = out[skip_real:]
        return out[:real] if real and int(out.shape[0]) > real else out
    body = frames[trim:] if int(frames.shape[0]) > trim else frames[:0]
    out = recover_held_frames(body, hold_map)
    return out[:real] if real and int(out.shape[0]) > real else out


def expand_real_tail_for_pin(
    tail: torch.Tensor,
    *,
    dilate: int,
    hold_map: Sequence[int] | None = None,
) -> torch.Tensor:
    """Expand a real-time tail into the slowed timebase for a slowed segment pin."""
    d = max(1, int(dilate))
    if int(tail.shape[0]) < 1:
        return tail
    if hold_map is None:
        return expand_frames(tail, [d] * int(tail.shape[0]))[0]
    holds = [max(1, int(h)) for h in hold_map]
    if len(holds) != int(tail.shape[0]):
        raise ValueError("motion retime: tail hold map length mismatch.")
    return expand_frames(tail, holds)[0]


def resolve_pin_real_frames(window_slowed: int, dilate: int) -> int:
    d = max(1, int(dilate))
    return max(1, int(window_slowed) // d)


def build_hold_map(
    clip: torch.Tensor,
    *,
    mode: str = "uniform",
    dilate: int = DEFAULT_DILATE,
    gate_abs: float = DEFAULT_GATE_ABS,
    gate_rel: float = DEFAULT_GATE_REL,
    bridge: int = DEFAULT_BRIDGE_FRAMES,
    ramp: int = DEFAULT_RAMP_FRAMES,
) -> tuple[list[int], float]:
    n = int(clip.shape[0]) if torch.is_tensor(clip) else 0
    mode = str(mode or "uniform").strip().lower()
    if mode not in MOTION_MODES:
        mode = "uniform"
    if mode == "adaptive":
        return build_adaptive_hold_map(
            n,
            clip,
            dilate=dilate,
            gate_abs=gate_abs,
            gate_rel=gate_rel,
            bridge=bridge,
            ramp=ramp,
        )
    return build_uniform_hold_map(n, dilate), motion_peak_score(clip)


def slowed_run_length(hold_map: Sequence[int]) -> int:
    """Slowed clip length before final align extension."""
    return hold_map_total(hold_map)


def audit_motion_segment(
    *,
    real_frames: int,
    dilate: int,
    hold_map: Sequence[int] | None = None,
) -> str:
    holds = list(hold_map) if hold_map is not None else build_uniform_hold_map(real_frames, dilate)
    total = sum(holds)
    slowed = _align(total)
    hot = sum(1 for h in holds if int(h) > 1)
    return (
        f"motion: {real_frames}f → {slowed}f slowed "
        f"(dilate={dilate}, hot={hot}f, groups={len(holds)}, align+{slowed - total})"
    )


def build_motion_plan(
    clip: torch.Tensor,
    motion_cfg: dict[str, Any],
    *,
    real_frames: int | None = None,
) -> dict[str, Any]:
    """Resolve one segment's hold map + slowed clip. Raises on guard failures."""
    real = int(real_frames if real_frames is not None else clip.shape[0])
    dilate = max(1, int(motion_cfg.get("dilate") or DEFAULT_DILATE))
    if dilate > MAX_DILATE:
        raise ValueError(
            f"motion fix: dilate {dilate} > max {MAX_DILATE}."
        )
    mode = str(motion_cfg.get("mode") or "uniform").strip().lower()
    hold_map, peak = build_hold_map(
        clip,
        mode=mode,
        dilate=dilate,
        gate_abs=float(motion_cfg.get("gate_abs") or DEFAULT_GATE_ABS),
        gate_rel=float(motion_cfg.get("gate_rel") or DEFAULT_GATE_REL),
        bridge=int(motion_cfg.get("bridge") or DEFAULT_BRIDGE_FRAMES),
        ramp=int(motion_cfg.get("ramp") or DEFAULT_RAMP_FRAMES),
    )
    if len(hold_map) != real:
        hold_map = build_uniform_hold_map(real, dilate)
    total = hold_map_total(hold_map)
    slowed_raw = _align(total)
    max_slowed = max(5, int(motion_cfg.get("max_slowed_frames") or DEFAULT_MAX_SLOWED_FRAMES))
    if slowed_raw > max_slowed:
        raise ValueError(
            f"motion fix: slowed length {slowed_raw}f exceeds max {max_slowed}f "
            f"(dilate={dilate}); lower the factor or disable motion for this segment."
        )
    slowed_clip, hold_map_used = expand_frames(clip, hold_map, target_frames=slowed_raw)
    if int(slowed_clip.shape[0]) != slowed_raw:
        raise RuntimeError(
            f"motion fix: slowed clip {int(slowed_clip.shape[0])}f != planned {slowed_raw}f."
        )
    return {
        "enabled": True,
        "mode": mode,
        "dilate": int(dilate),
        "slowed_clip": slowed_clip,
        "hold_map": hold_map_used,
        "real_frames": int(real),
        "slowed_frames": int(slowed_raw),
        "slowed_raw": int(total),
        "hot_frames": int(sum(1 for h in hold_map_used if int(h) > 1)),
        "peak_score": float(peak),
        "ack": str(motion_cfg.get("ack") or ""),
        "source_init_denoise": float(motion_cfg.get("source_init_denoise") or 0.0),
        "pin_window": dilation_pin_window(dilate),
        "pipeline": MOTION_PIPELINE_ID,
    }


def motion_pin_window_for_plan(motion: dict[str, Any] | None) -> int | None:
    if not motion:
        return None
    d = max(1, int(motion.get("dilate") or 1))
    return dilation_pin_window(d)


def motion_meta_for_handoff(motion: dict[str, Any] | None, *, slowed_trim: int, slowed_sample: int) -> dict[str, Any] | None:
    if not motion:
        return None
    return {
        "pipeline": motion.get("pipeline") or MOTION_PIPELINE_ID,
        "dilate": int(motion.get("dilate") or 1),
        "real_frames": int(motion.get("real_frames") or 0),
        "slowed_frames": int(motion.get("slowed_frames") or 0),
        "slowed_trim": int(slowed_trim),
        "slowed_sample": int(slowed_sample),
        "hold_map": [int(h) for h in motion.get("hold_map") or []],
        "pin_window": motion.get("pin_window"),
    }


def apply_source_init_latent(latent: dict, *, vae, clip: torch.Tensor) -> dict:
    """Write the VAE-encoded source clip into the empty AV latent's video stream.

    Keeps the audio stream (and any packing/keys) from the conditioning latent.
    """
    from .h3_motion_context import _repack_av_streams, _streams_from_latent

    streams = list(_streams_from_latent(latent))
    if not streams:
        raise ValueError("motion fix: target latent has no streams.")
    video = streams[0]
    if video.ndim == 4:
        video = video.unsqueeze(0)
    encoded = vae.encode(clip)
    if isinstance(encoded, dict):
        encoded = encoded.get("samples", encoded)
    if not torch.is_tensor(encoded) or encoded.ndim != 5:
        raise ValueError(
            f"motion fix: source VAE encode returned {type(encoded)!r}, expected [B,C,T,H,W]."
        )
    if int(encoded.shape[2]) != int(video.shape[2]):
        raise ValueError(
            "motion fix: source-init latent tokens "
            f"{int(encoded.shape[2])} != target {int(video.shape[2])}."
        )
    if tuple(encoded.shape[-2:]) != tuple(video.shape[-2:]):
        raise ValueError(
            "motion fix: source-init canvas "
            f"{tuple(encoded.shape[-2:])} != target {tuple(video.shape[-2:])}."
        )
    streams[0] = encoded.to(device=video.device, dtype=video.dtype)
    out = dict(latent)
    out.pop("noise_mask", None)
    out["samples"] = _repack_av_streams(streams, latent)
    return out


def plan_length_audit(
    entries: Iterable[tuple[int, int, int]],
) -> str:
    """``entries``: (segment_index, source_frames, planned_export_frames)."""
    lines = ["Length audit (source window → planned export, cumulative offset):"]
    offset = 0
    for index, source, planned in entries:
        offset += int(planned) - int(source)
        lines.append(
            f"  #{int(index) + 1}: {int(source)}f → {int(planned)}f "
            f"({int(planned) - int(source):+d}f, cum {offset:+d}f)"
        )
    return "\n".join(lines)
