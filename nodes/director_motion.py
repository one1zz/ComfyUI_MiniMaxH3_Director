"""Graph packer: Motion Fix config for MiniMax H3 Director.motion_fix.

Slows action-hot v2v/rv2v segments with integer frame holds, optionally
initialises the sample from the slowed source latent (partial denoise), then
recovers the original frame clock exactly. The source soundtrack is untouched.

Per-segment on/off and dilation live on the timeline rows (动作修复 /
motionFix + motionDilate) in both global and segment edit modes; this node only
provides defaults and the master switch.
"""

from __future__ import annotations

from ..director.motion_pack import (
    DEFAULT_SOURCE_INIT_DENOISE,
    MAX_DILATE,
    MAX_SOURCE_INIT_DENOISE,
    MMX_DIR_MOTION,
    MOTION_MODES,
    pack_motion,
    supported_dilations,
)
from ..director.motion_retime import (
    AUDIO_RECOVER_MODES,
    DEFAULT_AUDIO_RECOVER,
)

_CATEGORY = "MiniMaxH3"


class MiniMaxH3DirectorMotionFix:
    """Pack Motion Fix settings. Connect ``motion_fix`` to Director.motion_fix."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (
                    list(MOTION_MODES),
                    {
                        "default": "uniform",
                        "tooltip": (
                            "uniform = 每帧保持同倍率（可预测、最稳）。"
                            "adaptive = 只放慢动作过载帧（帧差热点），平段保持实时，"
                            "成本更低但热点判断可能漏/多。"
                        ),
                    },
                ),
                "dilate": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_DILATE,
                        "step": 1,
                        "tooltip": (
                            "帧保持倍率（放慢倍数）。越大高速动作越有生成余量，"
                            "显存/耗时近似按倍数增长。可被逐段倍率覆盖。"
                            "支持衔接的倍率（整除 5/22/39/56）："
                            + ", ".join(str(d) for d in supported_dilations())
                            + "；其余倍率下被放慢段按硬切处理。"
                        ),
                    },
                ),
                "source_init_denoise": (
                    "FLOAT",
                    {
                        "default": DEFAULT_SOURCE_INIT_DENOISE,
                        "min": 0.0,
                        "max": MAX_SOURCE_INIT_DENOISE,
                        "step": 0.05,
                        "tooltip": (
                            "源 latent 部分去噪初始化（0=只用参考视频条件）。"
                            "0.5–0.8 更贴近源动作/分镜，但换脸身份越弱；"
                            "建议 rv2v 参考图 + 0.6 起步，按素材微调。"
                        ),
                    },
                ),
            },
            "optional": {
                "audio_recover": (
                    list(AUDIO_RECOVER_MODES),
                    {
                        "default": DEFAULT_AUDIO_RECOVER,
                        "tooltip": (
                            "生成声音如何恢复正常速度（仅当声音=生成时生效）。"
                            "splice：按 hold 组首帧采样级拼回实时，接缝 2ms 淡化，保瞬态；"
                            "stretch：整体变速不变调（torchaudio 相位声码器，可能略糊）；"
                            "off：生成声音 + 动作修复无法保证音画同步，直接终止报错。"
                        ),
                    },
                ),
                "gate_abs": (
                    "FLOAT",
                    {
                        "default": 2.0,
                        "min": 0.0,
                        "max": 100.0,
                        "step": 0.1,
                        "tooltip": (
                            "adaptive 模式的绝对动作闸（0–255 缩略图帧差峰值）。"
                            "低于此值直接跳过放慢；社区实测 2.5 起步。"
                        ),
                    },
                ),
                "gate_rel": (
                    "FLOAT",
                    {
                        "default": 0.35,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.05,
                        "tooltip": "adaptive 模式的相对闸（相对本段峰值），两个闸取大者。",
                    },
                ),
                "bridge": (
                    "INT",
                    {"default": 2, "min": 0, "max": 20, "step": 1,
                     "tooltip": "adaptive：填补热点之间的短空档（帧）。"},
                ),
                "ramp": (
                    "INT",
                    {"default": 1, "min": 0, "max": 20, "step": 1,
                     "tooltip": "adaptive：热点两端各扩展的缓冲帧数。"},
                ),
                "min_frames": (
                    "INT",
                    {"default": 36, "min": 5, "max": 512, "step": 1,
                     "tooltip": "短于此帧数的段跳过 motion（收益低、开销高）。"},
                ),
                "max_slowed_frames": (
                    "INT",
                    {"default": 362, "min": 5, "max": 3600, "step": 1,
                     "tooltip": "放慢后总长的上限（H3 训练区间约 124–362，更长未验证）。"},
                ),
                "fail_fallback": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "开：某段 motion 失败/OOM 时自动按普通方式重跑该段，"
                            "不影响其它段。关：直接报错中断。"
                        ),
                    },
                ),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types=None, **_kwargs):
        return True

    RETURN_TYPES = (MMX_DIR_MOTION,)
    RETURN_NAMES = ("motion_fix",)
    FUNCTION = "pack"
    CATEGORY = _CATEGORY
    DESCRIPTION = (
        "MiniMax H3 Director Motion Fix: connect to Director.motion_fix. "
        "Per-segment 动作修复 checkboxes on the timeline select segments; "
        "this node supplies mode / dilation default / source-init denoise. "
        "Slowed segments export exactly the source window; original audio is "
        "never retimed. Unconnected = current single-pass behavior."
    )

    def pack(
        self,
        mode="uniform",
        dilate=2,
        source_init_denoise=DEFAULT_SOURCE_INIT_DENOISE,
        audio_recover=DEFAULT_AUDIO_RECOVER,
        gate_abs=2.0,
        gate_rel=0.35,
        bridge=2,
        ramp=1,
        min_frames=36,
        max_slowed_frames=362,
        fail_fallback=True,
        **kwargs,
    ):
        del kwargs
        return (
            pack_motion(
                mode=mode,
                dilate=dilate,
                source_init_denoise=source_init_denoise,
                audio_recover=audio_recover,
                gate_abs=gate_abs,
                gate_rel=gate_rel,
                bridge=bridge,
                ramp=ramp,
                min_frames=min_frames,
                max_slowed_frames=max_slowed_frames,
                fail_fallback=bool(fail_fallback),
            ),
        )
