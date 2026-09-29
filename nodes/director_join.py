"""Standalone lossless-join node for MiniMax H3 Director segment exports.

The node never talks to an executing Director. It joins an explicit ordered
file list when provided (the frontend picker writes it), otherwise resolves a
run directory (empty = newest). Video streams are copied; audio is rebuilt from
the per-segment ``seg_XXXX.wav`` sidecars or the run's ``director_timeline.wav``
as PCM, so joins are click-free and lossless.
"""

from __future__ import annotations

import logging

from ..director.segment_join import join_from_spec

log = logging.getLogger("ComfyUI-MiniMaxH3-Director.nodes.join")

_CATEGORY = "MiniMaxH3"


class MiniMaxH3DirectorJoinSegments:
    """Join segment exports losslessly, from a directory or an ordered file list."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": (
                            "分段导出目录（含 seg_XXXX.mp4）。留空 = 取最新一次"
                            "分段导出（推荐，一键）。也可填父目录 "
                            "minimax_seg_export（取最新一次）。"
                            "高级：files 非空时忽略此项。"
                        ),
                    },
                ),
                "files": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "高级：手动顺序（每行一个绝对路径，顺序即拼接顺序）。"
                            "留空则用目录里的 seg_XXXX.mp4；两者同时存在时以此为准。"
                        ),
                    },
                ),
                "output_name": (
                    "STRING",
                    {
                        "default": "director_joined",
                        "multiline": False,
                        "tooltip": "输出文件名（不含扩展名）。",
                    },
                ),
                "output_dir": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "输出目录；留空则与第一个视频同目录。",
                    },
                ),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types=None, **_kwargs):
        return True

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_path", "report")
    FUNCTION = "join"
    CATEGORY = _CATEGORY
    DESCRIPTION = (
        "Losslessly join MiniMax H3 Director segment exports. Queue it with all "
        "inputs left empty to join the newest segment-export run (one-click). "
        "Video: -c:v copy. Audio: PCM rebuilt from seg_*.wav or "
        "director_timeline.wav (no AAC priming clicks). Optional directory / "
        "ordered file list override the auto pick. Returns the joined path and a "
        "report with a duration sanity check."
    )

    def join(self, directory="", files="", output_name="director_joined", output_dir=""):
        result = join_from_spec(
            directory=directory,
            files_text=files,
            output_name=output_name,
            output_dir=output_dir,
        )
        log.info("MiniMax H3 Director join node wrote: %s", result.get("output"))
        return (str(result.get("output") or ""), str(result.get("report") or ""))
