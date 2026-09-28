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
                            "分段导出目录（含 seg_XXXX.mp4）。可填父目录 "
                            "minimax_seg_export（取最新一次），留空取全局最新。"
                            "上方列表选择了文件时忽略此项。"
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
                            "手动顺序（每行一个绝对路径，顺序即拼接顺序）。"
                            "上方的拖拽列表会自动写入这里；两者同时存在时以此为准。"
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
        "Losslessly join MiniMax H3 Director segment exports (any historical run). "
        "Video: -c:v copy. Audio: PCM rebuilt from seg_*.wav or director_timeline.wav "
        "(no AAC priming clicks). Accepts an ordered file list from the drag-and-drop "
        "picker, or a directory. Returns the joined path and a report with a duration "
        "sanity check."
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
