"""Test scaffolding for MiniMax H3 Director.

The pure-logic tests (frame/window/audio math, join helpers, capability matrix)
must run on a machine without torch/GPU. When torch is missing we install a
minimal stub good enough to import the modules; the tensor-heavy tests opt in
via ``pytest.importorskip("torch")`` and are skipped in that case.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

# Make ``import director`` work without relying on pytest's path config.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _install_torch_stub() -> None:
    if importlib.util.find_spec("torch") is not None:
        return
    if "torch" in sys.modules:
        return
    torch = types.ModuleType("torch")

    class _Tensor:
        pass

    torch.Tensor = _Tensor
    torch.is_tensor = lambda value: isinstance(value, _Tensor)
    torch.long = "long"
    torch.float32 = "float32"
    torch.float64 = "float64"
    torch.int16 = "int16"
    torch.__mmx_test_stub__ = True
    sys.modules["torch"] = torch


_install_torch_stub()


def _install_folder_paths_stub() -> None:
    """``director.segment_join`` imports folder_paths at module import."""
    if importlib.util.find_spec("folder_paths") is not None:
        return
    if "folder_paths" in sys.modules:
        return
    mod = types.ModuleType("folder_paths")
    mod.get_output_directory = lambda: "/tmp/opencode/mmx_test_output"
    mod.get_input_directory = lambda: "/tmp/opencode/mmx_test_input"
    sys.modules["folder_paths"] = mod


_install_folder_paths_stub()

