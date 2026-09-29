"""Lossless-join helpers: ordering, audio selection and WAV concatenation."""

from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

from director import segment_join as sj


def _wav(path: Path, *, sr: int = 32000, frames: int = 320, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * frames * channels)


def _run_dir(tmp_path: Path, n: int = 3, *, wavs: bool = True, timeline: bool = True):
    for i in range(n):
        (tmp_path / f"seg_{i:04d}.mp4").write_bytes(b"x")
        if wavs:
            _wav(tmp_path / f"seg_{i:04d}.wav")
    if timeline:
        _wav(tmp_path / "director_timeline.wav", frames=960)
    return tmp_path


def test_final_segments_sorted_and_rejects_gaps(tmp_path):
    _run_dir(tmp_path, n=3)
    files = sj._final_segments(tmp_path)
    assert [p.name for p in files] == ["seg_0000.mp4", "seg_0001.mp4", "seg_0002.mp4"]

    # A real index gap (0,2) must be rejected, not silently mis-joined.
    (tmp_path / "seg_0001.mp4").unlink()
    with pytest.raises(RuntimeError):
        sj._final_segments(tmp_path)


def test_pre_and_pn_files_are_ignored(tmp_path):
    _run_dir(tmp_path, n=2)
    (tmp_path / "seg_0000_pre.mp4").write_bytes(b"p")
    (tmp_path / "seg_0000_p2.mp4").write_bytes(b"p")
    assert [p.name for p in sj._final_segments(tmp_path)] == ["seg_0000.mp4", "seg_0001.mp4"]


def test_audio_full_set_prefers_timeline(tmp_path):
    _run_dir(tmp_path)
    files = sj._final_segments(tmp_path)
    audio, note = sj._resolve_audio(files, tmp_path)
    assert audio is not None and audio.name == "director_timeline.wav"
    assert "整轨" in note


def test_audio_subset_and_reorder_use_seg_wavs(tmp_path):
    _run_dir(tmp_path)
    files = sj._final_segments(tmp_path)
    audio, note = sj._resolve_audio([files[2], files[0]], tmp_path)
    assert audio is not None and audio.name == "_joined_audio.wav"
    with wave.open(str(audio)) as w:
        assert w.getnframes() == 640  # two 320-frame sidecars, in selection order
    assert "2 个段 WAV" in note


def test_audio_missing_reports_video_only(tmp_path):
    _run_dir(tmp_path, wavs=False, timeline=False)
    files = sj._final_segments(tmp_path)
    audio, note = sj._resolve_audio(files, tmp_path)
    assert audio is None
    assert "无音频" in note


def test_concat_wavs_rejects_mismatched_format(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _wav(a, sr=32000)
    _wav(b, sr=44100)
    with pytest.raises(RuntimeError):
        sj._concat_wavs([a, b], tmp_path / "out.wav")


def test_concat_list_escapes_quotes(tmp_path):
    ugly = tmp_path / "it's a file.mp4"
    ugly.write_bytes(b"x")
    dest = tmp_path / "_list.txt"
    sj._concat_list([ugly], dest)
    text = dest.read_text(encoding="utf-8")
    assert text.startswith("file '")
    assert "'\\''" in text


def test_parse_file_list_ignores_blanks_and_comments(tmp_path):
    text = f'"{tmp_path / "a.mp4"}"\n# comment\n; b.mp4\n\n'
    parsed = sj.parse_file_list(text)
    assert [p.name for p in parsed] == ["a.mp4", "b.mp4"]


def test_safe_output_name_strips_paths_and_illegal():
    assert sj._safe_output_name("../../evil:name") == "evil_name"
    assert sj._safe_output_name("") == "director_joined"
    assert sj._safe_output_name("a b.mp4") == "a_b.mp4"


def test_resolve_run_dir_accepts_parent_or_run(tmp_path):
    run = tmp_path / "20260101_000000"
    run.mkdir()
    _run_dir(run, n=1)
    assert sj.resolve_run_dir(run) == run
    assert sj.resolve_run_dir(tmp_path) == run


def test_latest_run_summary_and_resolve_empty(tmp_path, monkeypatch):
    import folder_paths

    monkeypatch.setattr(folder_paths, "get_output_directory", lambda: str(tmp_path))
    base = tmp_path / "minimax_seg_export"
    for name, mtime in (("older", 1000), ("newer", 2000)):
        d = base / name
        d.mkdir(parents=True)
        (d / "seg_0000.mp4").write_bytes(b"x")
        os.utime(d, (mtime, mtime))

    summary = sj.latest_run_summary()
    assert summary is not None and summary["name"] == "newer"
    assert sj.resolve_run_dir("") == base / "newer"
    assert [r["name"] for r in sj.list_segment_runs()] == ["newer", "older"]


def test_latest_run_summary_none_when_empty(tmp_path, monkeypatch):
    import folder_paths

    monkeypatch.setattr(folder_paths, "get_output_directory", lambda: str(tmp_path))
    assert sj.latest_run_summary() is None
    with pytest.raises(RuntimeError):
        sj.resolve_run_dir("")
