"""Adaptive H3 latent chunk sizing: grid-aligned, and only when it helps."""

from __future__ import annotations

from director import h3_latent_chunk as hc

OVERLAP = 5


def test_grid_residue_matches_17k5():
    # t % 5 == 2  <=>  pixel_frames(t) == 17k+5
    for t in (2, 7, 12, 17, 22, 27, 32, 37, 107):
        assert hc.is_h3_grid_tokens(t)
    for t in (0, 1, 3, 4, 5, 6, 24, 30, 31):
        assert not hc.is_h3_grid_tokens(t)


def test_balanced_aligned_half_for_typical_clip():
    # 124px clip = 37 tokens -> split into ~half, snapped up to grid.
    assert hc.adaptive_chunk_tokens(37, OVERLAP) == 22
    plan = hc.chunk_plan(37, OVERLAP)
    assert plan["chunked"] is True
    assert plan["chunks"] == 2
    assert plan["grid_aligned"] is True
    assert plan["segment"] == 22 + 2 * OVERLAP < 37


def test_long_clip_still_two_chunks():
    # 362px clip = 107 tokens.
    assert hc.adaptive_chunk_tokens(107, OVERLAP) == 57
    plan = hc.chunk_plan(107, OVERLAP)
    assert plan["chunks"] == 2
    assert plan["segment"] < 107


def test_short_clips_fall_back_to_full_forward():
    # Splitting here would not lower peak memory, so no chunking.
    for t in (12, 17, 22, 27):
        assert hc.adaptive_chunk_tokens(t, OVERLAP) == 0
        plan = hc.chunk_plan(t, OVERLAP)
        assert plan["chunked"] is False
        assert plan["chunks"] == 1
        assert plan["segment"] == t


def test_chunk_never_raises_peak_and_is_grid_aligned():
    for t in range(1, 400):
        chunk = hc.adaptive_chunk_tokens(t, OVERLAP)
        if chunk == 0:
            continue
        assert hc.is_h3_grid_tokens(chunk), t
        assert chunk + 2 * OVERLAP < t, t  # segment strictly shorter than full
        assert -(-t // chunk) == 2, t  # exactly two balanced pieces
