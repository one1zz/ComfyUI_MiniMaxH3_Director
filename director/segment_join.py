"""Lossless join for MiniMax H3 Director segment exports.

Segment mp4s carry per-file AAC (`write_frames_to_mp4`), so concatenating them
directly adds encoder priming/padding at every join. This module joins the
video streams with ``-c:v copy`` and replaces the audio with the lossless
``director_timeline.wav`` or the per-segment ``seg_XXXX.wav`` sidecars written
by segmented export (PCM in, PCM out — no re-encode of picture or sound).

Pure IO/ffmpeg helpers; the HTTP route and the Director output bar call in.
"""

from __future__ import annotations

import logging
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import folder_paths

log = logging.getLogger("ComfyUI-MiniMax-H3-Director.segment_join")

SEG_EXPORT_BASE = "minimax_seg_export"
_FINAL_SEG_RE = re.compile(r"^seg_(\d{4})\.mp4$")


def _base_dir() -> Path:
    return Path(folder_paths.get_output_directory()) / SEG_EXPORT_BASE


def _within_base(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(_base_dir().resolve())
    except Exception:
        try:
            base = str(_base_dir().resolve())
            return str(path.resolve()).startswith(base)
        except Exception:
            return False


def remember_run_dir(node_id: str | None, run_dir: Path | None) -> None:
    """Stamp the node -> latest segmented-export run dir pointer (best effort)."""
    if not node_id or run_dir is None:
        return
    try:
        latest = _base_dir() / "_latest"
        latest.mkdir(parents=True, exist_ok=True)
        (latest / f"{node_id}.txt").write_text(str(run_dir), encoding="utf-8")
    except OSError as exc:
        log.debug("Segment join pointer skipped: %s", exc)


def latest_run_dir(node_id: str | None) -> Path | None:
    """Resolve the newest segmented-export dir for ``node_id``.

    Uses the per-node pointer when available, else the newest run dir that
    actually contains ``seg_0000.mp4`` (shared fallback for older runs).
    """
    base = _base_dir()
    if node_id:
        pointer = base / "_latest" / f"{node_id}.txt"
        if pointer.is_file():
            try:
                candidate = Path(pointer.read_text(encoding="utf-8").strip())
                if candidate.is_dir() and _within_base(candidate):
                    return candidate
            except OSError:
                pass
    try:
        cands = [
            d
            for d in base.iterdir()
            if d.is_dir()
            and not d.name.startswith("_")
            and (d / "seg_0000.mp4").is_file()
        ]
    except OSError:
        return None
    return max(cands, key=lambda d: d.stat().st_mtime) if cands else None


def _final_segments(run_dir: Path) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    try:
        for entry in run_dir.iterdir():
            m = _FINAL_SEG_RE.match(entry.name)
            if m and entry.is_file():
                found.append((int(m.group(1)), entry))
    except OSError as exc:
        raise RuntimeError(f"无法读取分段目录：{exc}") from exc
    found.sort()
    if not found:
        raise RuntimeError("目录里没有 seg_XXXX.mp4（只有 _pre/_pN 等中间文件？）")
    indices = [i for i, _ in found]
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise RuntimeError(f"分段文件不连续：{indices}")
    return found


def _concat_wavs(wavs: list[Path], dest: Path) -> None:
    params: tuple[int, int, int] | None = None
    payloads: list[bytes] = []
    for path in wavs:
        if not path.is_file():
            raise RuntimeError(f"缺少段 WAV：{path.name}（请用新版本重新分段导出）")
        with wave.open(str(path), "rb") as w:
            cur = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params is None:
                params = cur
            elif cur != params:
                raise RuntimeError(
                    f"段 WAV 格式不一致：{path.name} {cur} != {params}"
                )
            payloads.append(w.readframes(w.getnframes()))
    if params is None:
        raise RuntimeError("没有可拼接的段 WAV")
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(params[0])
        out.setsampwidth(params[1])
        out.setframerate(params[2])
        for frames in payloads:
            out.writeframes(frames)


def _concat_list(segments: list[Path], dest: Path) -> None:
    lines = []
    for path in segments:
        escaped = path.as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def join_run_dir(run_dir: Path) -> dict[str, Any]:
    """Join one segment-export run dir. Returns ``{output, audio, segments}``."""
    from ..lib.video_export import _ffmpeg_bin

    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg 不可用（安装 FFmpeg 到 PATH 或 pip install imageio-ffmpeg）"
        )
    if not run_dir.is_dir():
        raise RuntimeError(f"目录不存在：{run_dir}")

    found = _final_segments(run_dir)
    segments = [path for _, path in found]

    # Lossless audio: whole-timeline WAV when present, else per-segment sidecars.
    timeline_wav = run_dir / "director_timeline.wav"
    if timeline_wav.is_file():
        audio_path = timeline_wav
    else:
        wavs = [run_dir / f"seg_{idx:04d}.wav" for idx, _ in found]
        audio_path = run_dir / "_joined_audio.wav"
        _concat_wavs(wavs, audio_path)

    list_path = run_dir / "_concat_list.txt"
    _concat_list(segments, list_path)

    def _run(dest: Path, audio_codec: str) -> tuple[int, str]:
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            audio_codec,
            "-shortest",
        ]
        if dest.suffix.lower() == ".mp4":
            cmd += ["-movflags", "+faststart"]
        cmd.append(str(dest))
        proc = subprocess.run(cmd, capture_output=True)
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        return int(proc.returncode or 0), err

    out_mp4 = run_dir / "director_joined.mp4"
    out_mkv = run_dir / "director_joined.mkv"
    for stale in (out_mp4, out_mkv):
        try:
            if stale.exists():
                stale.unlink()
        except OSError:
            pass
    code, err = _run(out_mp4, "pcm_s16le")
    if code == 0 and out_mp4.is_file() and out_mp4.stat().st_size > 0:
        return {"output": str(out_mp4), "audio": str(audio_path), "segments": len(segments)}

    # Some muxers reject PCM-in-MP4; MKV always accepts it and stays lossless.
    code, err_mkv = _run(out_mkv, "pcm_s16le")
    if code == 0 and out_mkv.is_file() and out_mkv.stat().st_size > 0:
        return {"output": str(out_mkv), "audio": str(audio_path), "segments": len(segments)}

    raise RuntimeError(f"无损拼接失败：{err or err_mkv or 'ffmpeg error'}")
