"""Wiring guards for the one-click join node."""

from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_join_route_registered():
    src = _read("director/http_routes.py")
    assert "minimax_join_segments" in src
    assert '"/minimax/director/join_segments"' in src
    assert "asyncio.to_thread" in src


def test_join_node_defaults_to_latest():
    src = _read("nodes/director_join.py")
    assert "one-click" in src.lower() or "一键" in src


def test_join_ui_has_one_click_button_and_route():
    src = _read("web/js/minimax_join.js")
    assert "joinNode.oneClick" in src
    assert "/minimax/director/join_segments" in src
    assert "joinNode.joinFailed" in src


def test_join_i18n_has_keys_in_both_locales():
    src = _read("web/js/minimax_i18n.js")
    for key in (
        "joinNode.oneClick",
        "joinNode.joining",
        "joinNode.done",
        "joinNode.joinFailed",
        "joinNode.advanced",
    ):
        assert src.count(f'"{key}"') == 2, f"{key} must exist in ZH and EN"
