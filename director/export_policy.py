"""Output export-policy helpers (dependency-free, unit-testable).

Lives outside ``plan.py`` so the pure policy logic can be imported without
torch / numpy / ComfyUI. ``plan.py`` re-exports these names for existing
callers.
"""

from __future__ import annotations


def flag_true(value, default: bool = False) -> bool:
    """Parse a tri-state-ish UI flag (None -> default, strings honoured)."""
    if value is None:
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def resolve_exact_export(output_block: dict | None) -> bool | None:
    """Source-audio-safe exact export. Tri-state: None = unset, else explicit."""
    out = output_block if isinstance(output_block, dict) else {}
    raw = out.get("exactExport")
    if raw is None:
        raw = out.get("exact_export")
    if raw is None:
        return None
    return flag_true(raw, False)


def exact_export_setting(
    output_block: dict | None, *, continuity_enabled: bool = False
) -> tuple[bool, bool]:
    """Return ``(value, explicit)`` for exact export.

    Explicit user choice wins. Unset + source audio + segment continuity
    auto-enables exact export (keeps the source soundtrack on the real clock);
    every other unset case keeps the legacy keep-full behavior (off).
    """
    raw = resolve_exact_export(output_block)
    if raw is not None:
        return bool(raw), True
    out = output_block if isinstance(output_block, dict) else {}
    audio = str(out.get("audioMode") or out.get("audio_mode") or "").strip().lower()
    auto = bool(continuity_enabled and audio == "source")
    return auto, False


__all__ = ["flag_true", "resolve_exact_export", "exact_export_setting"]
