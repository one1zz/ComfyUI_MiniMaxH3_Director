# Changelog

## Unreleased — motion-fix 收敛重构（`refactor/motion-fix-v2`）

以 `feature/motion-fix` 为基础的结构收敛与正确性修复，不改 `motion_retime` 的数学内核。

### 修复
- 动作修复：实时→放慢接缝的音频展开长度改用实际“钉入窗口”（原先误用上下文帧数，导致音频只覆盖视频钉入的一小段、时基错位）。
- 动作修复：前后段倍率不同时不再切上一段放慢音频 latent，改用实时音频展开并提示。
- 缓存/选择性运行：上一段 motion 元数据不完整时改为硬切并提示，避免把放慢坐标当实时坐标。
- 导出：`exactExport` 改为三态，未显式设置且「原声 + 段间引导」时自动启用并提示。
- 放慢上限：默认 362 → 512（软限，超过仅提示）；超过约 362 提示“超出训练区间”；仅 >3600 硬报错。
- 动作包（`*.mmxpack`）导入导出保留逐段动作修复开关与倍率。
- 缓存面板：补 `motion_fix` witness，修复接了 Motion Fix 后“先确认一采”误报不匹配。

### 变更（默认值）
- `exactExport`、`refPadToGrid` **默认关闭**，需在输出栏显式开启（原声 + 段间引导会自动启用精确导出）。
- 因默认值与行为变化，段级缓存版本号提升（旧缓存一次性失效重采）。

### 工程
- 新增能力矩阵单一事实来源 `motion_pack.motion_capabilities()`，运行报告/文档/测试同源。
- 新增纯决策函数 `select_pin_window()` / `decide_pin_audio()` / `motion_meta_usable()`；执行器不再重复计算。
- 合并 `apply_motion_context` / `apply_latent_continue` 的跨时基音频分支。
- 新增 `tests/`（pytest）与 `run_tests.py`（跨平台入口，见下）。

### 未决 / 后续
- 放大二采 + 引导+重绘：前缀硬锁不保留（会提示）。
- SelfLift 与动作修复组合：按“明确降级”处理（会提示）。
- 结构上仍可进一步引入 `MotionPlan` dataclass（当前以纯决策函数达成单一来源）。

### 测试
```
python run_tests.py
```
仓库根是 ComfyUI 自定义节点包（含相对导入的 `__init__.py`），请用该入口从 `tests/` 运行；无 torch 环境会自动跳过张量用例。
