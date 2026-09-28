"""Graph node: losslessly join a MiniMax H3 Director segment-export run.

Unlike the Director output-bar button (latest run of that node), this node can
join any historical run directory and does not need a Director node.
"""

from __future__ import annotations

import logging

from ..director.segment_join import join_run_dir, resolve_run_dir

log = logging.getLogger("ComfyUI-MiniMaxH3-Director.nodes.join")

_CATEGORY = "MiniMaxH3"


class MiniMaxH3DirectorJoinSegments:
    """Join segmented export: video stream copy + lossless PCM audio."""

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
                        ),
                    },
                ),
                "output_name": (
                    "STRING",
                    {
                        "default": "director_joined",
                        "multiline": False,
                        "tooltip": "输出文件名（不含扩展名），落在同一目录。",
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
        "Losslessly join a MiniMax H3 Director segment export (any historical run "
        "dir). Video streams use -c:v copy; audio is rebuilt from seg_*.wav or "
        "director_timeline.wav as PCM, so joins have no AAC priming clicks. "
        "Returns the joined file path and a report."
    )

    def join(self, directory="", output_name="director_joined"):
        run_dir = resolve_run_dir(directory)
        result = join_run_dir(run_dir, output_name=output_name)
        report = (
            f"Segments: {int(result.get('segments') or 0)}\n"
            f"Run dir: {run_dir}\n"
            f"Audio: {result.get('audio')}\n"
            f"Video: {result.get('output')}"
        )
        log.info("MiniMax H3 Director join node wrote: %s", result.get("output"))
        return (str(result.get("output") or ""), report)
