"""Capability matrix: every conflict must resolve to a hint/degradation."""

from __future__ import annotations

from director import motion_pack as mp


def _codes(caps):
    return {cap.code for cap in caps}


def _levels(caps):
    return {cap.code: cap.level for cap in caps}


def test_disabled_and_non_motion_task():
    caps = mp.motion_capabilities(enabled=False)
    assert _codes(caps) == {"motion_off"}
    assert caps[0].level == mp.CAP_OK

    caps = mp.motion_capabilities(enabled=True, task_key="t2v")
    assert _codes(caps) == {"task"}
    assert caps[0].level == mp.CAP_UNSUPPORTED


def test_selflift_is_explicit_degradation():
    caps = mp.motion_capabilities(enabled=True, task_key="v2v", selflift=True)
    assert _levels(caps)["selflift"] == mp.CAP_DEGRADED
    assert "跳过动作修复" in "".join(mp.motion_capability_messages(caps))


def test_trained_range_and_soft_limit():
    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", dilate=3, slowed_frames=379, max_slowed_frames=512
    )
    assert _levels(caps)["trained_range"] == mp.CAP_HINT
    assert "soft_limit" not in _codes(caps)

    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", dilate=4, slowed_frames=600, max_slowed_frames=512
    )
    assert _codes(caps) >= {"trained_range", "soft_limit"}


def test_source_audio_continuity_implies_exact():
    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", audio_mode="source", continuity="guide",
        exact_export=False,
    )
    assert _levels(caps)["source_exact"] == mp.CAP_HINT

    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", audio_mode="source", continuity="guide",
        exact_export=True,
    )
    assert "source_exact" not in _codes(caps)


def test_window_promotion_and_no_window():
    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", dilate=3, context_frames=22, refine="refine",
    )
    assert _levels(caps)["window_promotion"] == mp.CAP_HINT

    caps = mp.motion_capabilities(enabled=True, task_key="v2v", dilate=5)
    assert _levels(caps)["no_window"] == mp.CAP_HINT


def test_orthogonal_toggles_have_notes():
    caps = mp.motion_capabilities(
        enabled=True, task_key="rv2v", semantic_bridge=True, face_refine=True,
    )
    assert _levels(caps)["semantic_bridge"] == mp.CAP_HINT
    assert _levels(caps)["face_refine"] == mp.CAP_OK


def test_clean_combo_is_ok():
    caps = mp.motion_capabilities(
        enabled=True, task_key="v2v", dilate=2, slowed_frames=260, context_frames=22,
        continuity="guide", audio_mode="generate", refine="off",
    )
    assert _codes(caps) == {"ok"}


def test_continue_refine_keeps_lock_upscale_hints():
    same = mp.motion_capabilities(
        enabled=True, task_key="v2v", continuity="continue", refine="refine",
    )
    assert _levels(same)["continue_refine"] == mp.CAP_OK

    up = mp.motion_capabilities(
        enabled=True, task_key="v2v", continuity="continue", refine="upscale",
    )
    assert _levels(up)["continue_refine"] == mp.CAP_HINT


def test_message_helper_filters_by_level():
    caps = mp.motion_capabilities(enabled=True, task_key="v2v", selflift=True)
    msgs = mp.motion_capability_messages(caps)
    assert msgs and all(isinstance(m, str) and m for m in msgs)
    assert mp.motion_capability_messages(caps, levels=(mp.CAP_OK,)) == []


def test_motion_meta_usable_requires_recovery_fields():
    assert mp.motion_meta_usable(
        {"real_frames": 124, "dilate": 2, "hold_map": [2] * 124}
    )
    assert not mp.motion_meta_usable(None)
    assert not mp.motion_meta_usable({})
    assert not mp.motion_meta_usable({"real_frames": 124, "dilate": 2})
    assert not mp.motion_meta_usable({"real_frames": 0, "dilate": 2, "hold_map": [2]})


def test_motion_meta_for_handoff_round_trips():
    from director import motion_retime as mr

    plan = {
        "pipeline": mr.MOTION_PIPELINE_ID,
        "dilate": 2,
        "real_frames": 124,
        "slowed_frames": 260,
        "hold_map": [2] * 124,
        "pin_window": 56,
        "audio_recover": "splice",
    }
    meta = mr.motion_meta_for_handoff(plan, slowed_trim=56, slowed_sample=328)
    assert meta is not None
    assert meta["slowed_trim"] == 56 and meta["slowed_sample"] == 328
    assert meta["hold_map"] == [2] * 124
    assert mp.motion_meta_usable(meta)
    assert mr.motion_meta_for_handoff(None, slowed_trim=0, slowed_sample=0) is None


def test_select_pin_window_policy():
    # Context fits the slowed budget and divides the dilation: use it as-is.
    d = mp.select_pin_window(preferred=22, dilate=2, available_slowed=260, planned=56)
    assert d.window == 22 and not d.promoted and d.real_frames == 11
    # Context not divisible: promote to the dilation's legal window.
    d = mp.select_pin_window(preferred=22, dilate=3, available_slowed=270, planned=39)
    assert d.window == 39 and d.promoted and d.real_frames == 13
    # Not enough slowed frames available: hard cut.
    d = mp.select_pin_window(preferred=22, dilate=2, available_slowed=10, planned=56)
    assert d.window is None and not d.promoted


def test_decide_pin_audio_sources():
    # Same dilation + prev AV -> slice the previous slowed latent.
    d = mp.decide_pin_audio(
        prev_motion_meta={"dilate": 2}, has_prev_av=True, has_prev_audio=True,
        dilate=2, pin_window=22,
    )
    assert d.source == "latent" and d.slowed_frames == 22
    assert "latent" in d.note

    # Prev real-time -> expand the previous audio to the pin window.
    d = mp.decide_pin_audio(
        prev_motion_meta=None, has_prev_av=False, has_prev_audio=True,
        dilate=3, pin_window=39,
    )
    assert d.source == "expand" and d.slowed_frames == 39

    # Different dilation -> degrade to expand, with a timebase note.
    d = mp.decide_pin_audio(
        prev_motion_meta={"dilate": 2}, has_prev_av=True, has_prev_audio=True,
        dilate=3, pin_window=39,
    )
    assert d.source == "expand" and "倍率" in d.note

    # No previous audio -> video-only pin.
    d = mp.decide_pin_audio(
        prev_motion_meta=None, has_prev_av=False, has_prev_audio=False,
        dilate=2, pin_window=22,
    )
    assert d.source == "none"


def _all_capability_combos():
    tasks = ("v2v", "rv2v")
    dilates = (2, 3, 4, 7, 8)
    continuity = ("off", "guide", "continue")
    audio = ("generate", "source", "mute")
    refine = ("off", "refine", "upscale")
    slowed = (0, 260, 379, 600)
    for task in tasks:
        for dilate in dilates:
            for cont in continuity:
                for aud in audio:
                    for ref in refine:
                        for sf in slowed:
                            for sl in (False, True):
                                for sb in (False, True):
                                    for fr in (False, True):
                                        for ex in (False, True):
                                            yield dict(
                                                enabled=True,
                                                task_key=task,
                                                dilate=dilate,
                                                slowed_frames=sf,
                                                context_frames=22,
                                                continuity=cont,
                                                audio_mode=aud,
                                                refine=ref,
                                                selflift=sl,
                                                semantic_bridge=sb,
                                                face_refine=fr,
                                                exact_export=ex,
                                            )


def test_capability_matrix_is_total_and_never_raises():
    """L2: every effective combination resolves to a level (no silent gaps)."""
    levels = {mp.CAP_OK, mp.CAP_HINT, mp.CAP_DEGRADED, mp.CAP_UNSUPPORTED}
    n = 0
    for kwargs in _all_capability_combos():
        caps = mp.motion_capabilities(**kwargs)
        n += 1
        assert caps, f"empty capability list for {kwargs}"
        for cap in caps:
            assert cap.level in levels
            # Actionable (non-ok) notes must carry a message.
            if cap.level != mp.CAP_OK:
                assert cap.message, f"{cap.code} missing message for {kwargs}"
        codes = {c.code for c in caps}
        if kwargs["selflift"]:
            assert "selflift" in codes
        if (
            kwargs["audio_mode"] == "source"
            and kwargs["continuity"] != "off"
            and not kwargs["exact_export"]
        ):
            assert "source_exact" in codes
    assert n == 2 * 5 * 3 * 3 * 3 * 4 * 2 * 2 * 2 * 2
