"""Exact-export tri-state + auto-enable policy (H4)."""

from __future__ import annotations

from director.export_policy import exact_export_setting, resolve_exact_export


def test_resolve_is_tri_state():
    assert resolve_exact_export({}) is None
    assert resolve_exact_export({"exactExport": True}) is True
    assert resolve_exact_export({"exact_export": False}) is False
    assert resolve_exact_export({"exactExport": "off"}) is False
    assert resolve_exact_export("not a dict") is None


def test_explicit_choice_wins_over_auto():
    value, explicit = exact_export_setting(
        {"exactExport": False, "audioMode": "source"}, continuity_enabled=True
    )
    assert value is False and explicit is True
    value, explicit = exact_export_setting(
        {"exactExport": True, "audioMode": "generate"}, continuity_enabled=False
    )
    assert value is True and explicit is True


def test_auto_enables_only_for_source_plus_continuity():
    assert exact_export_setting(
        {"audioMode": "source"}, continuity_enabled=True
    ) == (True, False)
    assert exact_export_setting(
        {"audio_mode": "source"}, continuity_enabled=True
    ) == (True, False)
    assert exact_export_setting(
        {"audioMode": "source"}, continuity_enabled=False
    ) == (False, False)
    assert exact_export_setting(
        {"audioMode": "generate"}, continuity_enabled=True
    ) == (False, False)
    assert exact_export_setting({}, continuity_enabled=True) == (False, False)
