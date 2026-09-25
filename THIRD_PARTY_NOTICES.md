# Third-Party Notices / 第三方声明

本仓库整体以 Apache License 2.0 发布（见 `LICENSE`）。以下列出仓库内包含的第三方衍生内容及其许可。

## 1. bytedance/Bernini — prompt 增强模板（Apache-2.0）

`lib/official_pe_templates.py`（逐字引用的官方模板）、`lib/prompt_enhance_templates.py`（按官方 `prompt_enhancer` 对齐的改写模板）来源于 ByteDance 的 Bernini 项目：

- 上游：https://github.com/bytedance/Bernini
- 许可：Apache License 2.0
- 版权：Copyright (c) 2026 Bytedance Ltd. and/or its affiliate

## 2. Carasibana/ComfyUI-H3-FaceRefine — 脸部检测/裁剪/拼接（MIT）

`director/face_refine/track.py`、`director/face_refine/stitch.py`、`director/face_refine/inject.py` 改编自 Carasibana 的 ComfyUI-H3-FaceRefine：

- 上游：https://github.com/Carasibana/ComfyUI-H3-FaceRefine
- 许可：MIT
- 版权：Copyright (c) 2026 Carasibana

完整 MIT 许可文本：

```
MIT License

Copyright (c) 2026 Carasibana

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 3. 可选运行时依赖（不随本仓库分发）

以下依赖仅在用户环境按需 `pip install`，本仓库不包含其代码或权重：

- `ultralytics`（FaceRefine 可选）：AGPL-3.0，仅运行时 import；请勿将 YOLO 权重随仓库分发。
- `nvidia-vfx`（Refine `nvidia_rtx_vsr` 可选）：NVIDIA 专有软件。
- `opencv-python-headless`、`imageio-ffmpeg`、`scenedetect` 等：各自遵循其上游许可。

另：本插件运行时依赖 ComfyUI（GPL-3.0）及其 `comfy_extras` 接口，但未复制其源码。

> 思路/架构参考（`NikoDemon80/ComfyUI-H3-Motion-Context`、`LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler`、`slmonker/selflift-Avatar`、`speach1sdef178/MiniMax-H3-Semantic-Bridge` 等）见 README「致谢」，相关实现为本仓库原创代码。
