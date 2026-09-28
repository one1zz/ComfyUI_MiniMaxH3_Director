"""Lossless join for MiniMax H3 Director segment exports (standalone).

Segment mp4s carry per-file AAC, so concatenating them directly adds encoder
priming/padding at every join. This module joins an explicit, ordered list of
video files (or a whole run dir) with ``-c:v copy`` and rebuilds the audio from
the per-segment ``seg_XXXX.wav`` sidecars (or the run's ``director_timeline.wav``)
as PCM — no picture re-encode, no AAC priming clicks.

Used by the standalone ``MiniMaxH3DirectorJoinSegments`` node and the frontend
run/file picker. No dependency on an executing Director node.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import folder_paths

log = logging.getLogger("ComfyUI-MiniMax-H3-Director.segment_join")

SEG_EXPORT_BASE = "minimax_seg_export"
_FINAL_SEG_RE = re.compile(r"^seg_(\d{4})\.mp4$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _base_dir() -> Path:
    return Path(folder_paths.get_output_directory()) / SEG_EXPORT_BASE


def _safe_output_name(raw: str | None) -> str:
    name = _SAFE_NAME_RE.sub("_", str(raw or "")).strip("._")
    return name or "director_joined"


def _final_segments(run_dir: Path) -> list[Path]:
    """Final ``seg_XXXX.mp4`` files in index order (excludes _pre/_pN/_facepre)."""
    found: list[tuple[int, Path]] = []
    try:
        for entry in run_dir.iterdir():
            m = _FINAL_SEG_RE.match(entry.name)
            if m and entry.is_file():
                found.append((int(m.group(1)), entry))
    except OSError as exc:
        raise RuntimeError(f"无法读取目录：{exc}") from exc
    found.sort()
    if not found:
        raise RuntimeError("目录里没有 seg_XXXX.mp4（只有 _pre/_pN 等中间文件？）")
    indices = [i for i, _ in found]
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise RuntimeError(f"分段文件不连续：{indices}")
    return [p for _, p in found]


def list_segment_runs(limit: int = 40) -> list[dict[str, Any]]:
    """Recent segment-export runs for the frontend picker (newest first)."""
    base = _base_dir()
    try:
        dirs = [d for d in base.iterdir() if d.is_dir() and not d.name.startswith("_")]
    except OSError:
        return []
    runs: list[tuple[float, dict[str, Any]]] = []
    for d in dirs:
        if not (d / "seg_0000.mp4").is_file():
            continue
        try:
            files = _final_segments(d)
        except Exception:
            # Listing should still surface a run whose numeration is unusual.
            files = sorted(
                (p for p in d.glob("seg_*.mp4") if _FINAL_SEG_RE.match(p.name)),
                key=lambda p: p.name,
            )
            if not files:
                continue
        wavs = [p.with_suffix(".wav").is_file() for p in files]
        runs.append(
            (
                d.stat().st_mtime,
                {
                    "dir": str(d),
                    "name": d.name,
                    "count": len(files),
                    "files": [str(p) for p in files],
                    "names": [p.name for p in files],
                    "wavs": wavs,
                    "timeline_wav": (d / "director_timeline.wav").is_file(),
                },
            )
        )
    runs.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in runs[: max(1, int(limit))]]


def latest_run_dir() -> Path | None:
    runs = list_segment_runs(limit=1)
    return Path(runs[0]["dir"]) if runs else None


def resolve_run_dir(raw: str | Path | None) -> Path:
    """Resolve a path to a concrete run dir (empty = newest run overall)."""
    text = str(raw or "").strip()
    if not text:
        found = latest_run_dir()
        if found is None:
            raise RuntimeError("没有找到任何分段导出目录。")
        return found
    path = Path(text).expanduser()
    if not path.is_dir():
        raise RuntimeError(f"目录不存在：{path}")
    if (path / "seg_0000.mp4").is_file():
        return path
    try:
        cands = [
            d for d in path.iterdir() if d.is_dir() and (d / "seg_0000.mp4").is_file()
        ]
    except OSError as exc:
        raise RuntimeError(f"无法读取目录：{exc}") from exc
    if not cands:
        raise RuntimeError(f"目录里没有 seg_XXXX.mp4：{path}")
    return max(cands, key=lambda d: d.stat().st_mtime)


def parse_file_list(raw: str | None) -> list[Path]:
    """Newline/semicolon separated paths; blank lines and comments ignored."""
    out: list[Path] = []
    for line in str(raw or "").replace(";", "\n").splitlines():
        text = line.strip().strip('"').strip("'")
        if not text or text.startswith("#"):
            continue
        out.append(Path(text).expanduser())
    return out


def _concat_wavs(wavs: list[Path], dest: Path) -> None:
    params: tuple[int, int, int] | None = None
    payloads: list[bytes] = []
    for path in wavs:
        if not path.is_file():
            raise RuntimeError(f"缺少段 WAV：{path.name}")
        with wave.open(str(path), "rb") as w:
            cur = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params is None:
                params = cur
            elif cur != params:
                raise RuntimeError(f"段 WAV 格式不一致：{path.name} {cur} != {params}")
            payloads.append(w.readframes(w.getnframes()))
    if params is None:
        raise RuntimeError("没有可拼接的段 WAV")
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(params[0])
        out.setsampwidth(params[1])
        out.setframerate(params[2])
        for frames in payloads:
            out.writeframes(frames)


def _concat_list(files: list[Path], dest: Path) -> None:
    lines = []
    for path in files:
        escaped = path.as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ffprobe_duration(path: Path, ffprobe: str) -> float | None:
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return None
        return float((proc.stdout or b"").decode("utf-8").strip().splitlines()[0])
    except Exception:
        return None


def _resolve_audio(files: list[Path], output_dir: Path) -> tuple[Path | None, str]:
    """Pick the lossless audio for an ordered file list. Returns (path, note)."""
    run_dir = files[0].parent
    if all(p.parent == run_dir for p in files):
        full = None
        try:
            full = _final_segments(run_dir)
        except Exception:
            full = None
        if full is not None and full == files:
            timeline = run_dir / "director_timeline.wav"
            if timeline.is_file():
                return timeline, "整轨 director_timeline.wav"
    wavs = [p.with_suffix(".wav") for p in files]
    missing = [p.name for p in wavs if not p.is_file()]
    if not missing:
        dest = output_dir / "_joined_audio.wav"
        _concat_wavs(wavs, dest)
        return dest, f"{len(wavs)} 个段 WAV"
    if len(files) == 1 and not wavs[0].is_file():
        return None, "无音频"
    return (
        None,
        f"无音频（缺少 {len(missing)} 个段 WAV，如 {', '.join(missing[:2])}）",
    )


def join_files(
    files: list[Path],
    *,
    output_name: str = "director_joined",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Join an explicit ordered file list. Returns paths + a human report."""
    from ..lib.video_export import _ffmpeg_bin

    if not files:
        raise RuntimeError("没有可拼接的文件。")
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise RuntimeError("文件不存在：" + ", ".join(missing[:3]))
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg 不可用（安装 FFmpeg 到 PATH 或 pip install imageio-ffmpeg）"
        )

    dest_dir = Path(output_dir).expanduser() if output_dir else files[0].parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_output_name(output_name)

    audio_path, audio_note = _resolve_audio(files, dest_dir)
    list_path = dest_dir / f"_{safe}_list.txt"
    _concat_list(files, list_path)

    out_mp4 = dest_dir / f"{safe}.mp4"
    out_mkv = dest_dir / f"{safe}.mkv"
    for stale in (out_mp4, out_mkv):
        try:
            if stale.exists():
                stale.unlink()
        except OSError:
            pass

    def _run(dest: Path, audio_codec: str) -> tuple[int, str]:
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        cmd += ["-f", "concat", "-safe", "0", "-i", str(list_path)]
        if audio_path is not None:
            cmd += ["-i", str(audio_path)]
        cmd += ["-map", "0:v:0"]
        if audio_path is not None:
            cmd += ["-map", "1:a:0"]
        cmd += ["-c:v", "copy"]
        if audio_path is not None:
            cmd += ["-c:a", audio_codec]
        else:
            cmd += ["-an"]
        cmd += ["-avoid_negative_ts", "make_zero"]
        if dest.suffix.lower() == ".mp4":
            cmd += ["-movflags", "+faststart"]
        cmd.append(str(dest))
        proc = subprocess.run(cmd, capture_output=True)
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        return int(proc.returncode or 0), err

    code, err = _run(out_mp4, "pcm_s16le")
    output = out_mp4
    if not (code == 0 and out_mp4.is_file() and out_mp4.stat().st_size > 0):
        code2, err2 = _run(out_mkv, "pcm_s16le")
        if code2 == 0 and out_mkv.is_file() and out_mkv.stat().st_size > 0:
            output = out_mkv
        else:
            raise RuntimeError(f"无损拼接失败：{err or err2 or 'ffmpeg error'}")

    # Duration sanity: copied segments must add up to the joined stream.
    duration_note = ""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        expected = 0.0
        per_file_ok = True
        for path in files:
            d = _ffprobe_duration(path, ffprobe)
            if d is None:
                per_file_ok = False
                break
            expected += d
        actual = _ffprobe_duration(output, ffprobe) if per_file_ok else None
        if actual is not None:
            delta = abs(actual - expected)
            duration_note = f"时长 {actual:.3f}s / 预期 {expected:.3f}s"
            if delta > 0.75:
                duration_note += f"（差 {delta:.3f}s，请检查文件是否同编码/同画布）"

    try:
        list_path.unlink()
    except OSError:
        pass

    report = (
        f"文件：{len(files)} 个\n"
        f"音频：{audio_note}\n"
        f"输出：{output}\n"
        + (f"{duration_note}\n" if duration_note else "")
    )
    return {
        "output": str(output),
        "audio": str(audio_path) if audio_path is not None else "",
        "files": [str(p) for p in files],
        "segments": len(files),
        "report": report,
    }


def join_run_dir(run_dir: Path, *, output_name: str = "director_joined") -> dict[str, Any]:
    """Join a whole run dir (all final segments, in index order)."""
    return join_files(
        _final_segments(run_dir), output_name=output_name, output_dir=run_dir
    )


def join_from_spec(
    directory: str = "",
    files_text: str = "",
    output_name: str = "director_joined",
    output_dir: str = "",
) -> dict[str, Any]:
    """Node entry point: explicit file list wins over directory selection."""
    explicit = parse_file_list(files_text)
    if explicit:
        out = Path(output_dir).expanduser() if str(output_dir or "").strip() else None
        return join_files(explicit, output_name=output_name, output_dir=out)
    run_dir = resolve_run_dir(directory)
    return join_run_dir(run_dir, output_name=output_name)
