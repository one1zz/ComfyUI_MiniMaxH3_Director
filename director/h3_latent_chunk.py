"""Adaptive temporal chunk sizing for the H3 latent upscaler.

The upscaler's time axis is made of H3 latent tokens. H3 tokens cover a
repeating ``1/4/4/4/4`` pixel pattern (see ``h3_motion_context.FRAME_PER_TOKEN``),
so a token run of length ``t`` spans exactly ``17k+5`` pixel frames — a legal
H3 clip length — only when ``t % 5 == 2`` (5, 22, 39, ... tokens).

The upstream node hardcoded the chunk stride (16 -> 24 -> 32 across three
commits) with no derivation. We instead size it from the clip: split the
temporal axis into two grid-aligned halves, which is the fewest-seam way to
bring the peak segment below the full-clip length. When the split would not
actually shorten the padded forward (short clips), chunking is skipped so the
caller falls back to a single full forward.

This module is torch-free so the rule is unit-testable without a GPU.
"""

from __future__ import annotations

# H3 token grid: pixel_frames(t) == 17k+5  <=>  t % 5 == 2.
_H3_TOKEN_CYCLE = 5
_H3_GRID_RESIDUE = 2


def is_h3_grid_tokens(total_tokens: int) -> bool:
    """True when a token run of this length maps to a legal ``17k+5`` clip."""
    return int(total_tokens) % _H3_TOKEN_CYCLE == _H3_GRID_RESIDUE


def _snap_up_to_grid(tokens: int) -> int:
    """Round up to the nearest ``t % 5 == 2`` token count (min 2)."""
    t = max(_H3_GRID_RESIDUE, int(tokens))
    rem = (t - _H3_GRID_RESIDUE) % _H3_TOKEN_CYCLE
    if rem:
        t += _H3_TOKEN_CYCLE - rem
    return t


def adaptive_chunk_tokens(total_tokens: int, overlap: int) -> int:
    """Tokens per chunk for the H3 latent upscaler, or ``0`` to not chunk.

    ``overlap`` is the per-side blend/context width the forward adds around
    each chunk, so a chunk of ``c`` tokens produces a ``c + 2*overlap`` segment.
    We pick the smallest grid-aligned half of ``total_tokens`` and only accept
    it when that segment is strictly shorter than a full forward — otherwise
    chunking would raise peak memory instead of lowering it.
    """
    t = int(total_tokens)
    o = max(0, int(overlap))
    if t <= 0:
        return 0
    half = _snap_up_to_grid((t + 1) // 2)
    if half >= t - 2 * o:
        return 0
    return half


def chunk_plan(total_tokens: int, overlap: int) -> dict:
    """Describe the adaptive decision (for logging / node info)."""
    t = int(total_tokens)
    o = max(0, int(overlap))
    chunk = adaptive_chunk_tokens(t, o)
    if chunk <= 0:
        return {
            "tokens": t,
            "overlap": o,
            "chunk": 0,
            "chunks": 1,
            "chunked": False,
            "segment": t,
            "grid_aligned": is_h3_grid_tokens(t),
        }
    return {
        "tokens": t,
        "overlap": o,
        "chunk": chunk,
        "chunks": (t + chunk - 1) // chunk,
        "chunked": True,
        "segment": chunk + 2 * o,
        "grid_aligned": is_h3_grid_tokens(chunk),
    }
