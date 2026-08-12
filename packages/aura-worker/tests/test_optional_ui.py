"""The worker must import — and run headless — without the Gradio UI stack.

`gradio` is a phenotype: it draws the interactive Colab panel in ui.py and
nothing else. Importing it at module scope in controller.py made every consumer
of `aura_worker` pay for it, including headless nodes and the test suite, which
collapsed at collection when gradio's own transitive stack was incomplete.

These tests run in subprocesses because the question is what gets imported, and
`sys.modules` in the pytest process has already answered it.
"""

import os
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# Simulates an install without the [ui] extra.
BLOCK_UI_STACK = """
import sys

class _NoUIStack:
    BLOCKED = {"gradio", "nest_asyncio", "dotenv"}

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BLOCKED:
            raise ImportError(f"No module named {name!r}", name=name)
        return None

sys.meta_path.insert(0, _NoUIStack())
"""


def run_python(code: str) -> subprocess.CompletedProcess[str]:
    """Run code in a fresh interpreter that can see the worker sources."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(SRC), env.get("PYTHONPATH", "")) if p
    )
    return subprocess.run(  # nosec B603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )


def test_importing_the_package_does_not_import_gradio():
    result = run_python(
        "import sys, aura_worker\n"
        "assert 'gradio' not in sys.modules, 'gradio was dragged in'\n"
        "print('clean')"
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_public_api_imports_without_the_ui_stack():
    result = run_python(
        BLOCK_UI_STACK + "\n"
        "from aura_worker import AuraNode, Umbilical, VisionSkill, WorkerController\n"
        "print('imported')"
    )
    assert result.returncode == 0, result.stderr
    assert "imported" in result.stdout


def test_headless_start_gets_a_progress_callback_that_does_nothing():
    """start() reports progress; without the UI stack that must be a no-op,
    not a crash — the MLS-mode worker runs with no panel attached."""
    result = run_python(
        BLOCK_UI_STACK + "\n"
        "from aura_worker.controller import _ui_progress\n"
        "progress = _ui_progress()\n"
        "assert progress(0.3, desc='Pulling model') is None\n"
        "print('no-op')"
    )
    assert result.returncode == 0, result.stderr
    assert "no-op" in result.stdout


def test_launch_interactive_node_asks_for_the_ui_extra_when_it_is_missing():
    result = run_python(
        BLOCK_UI_STACK + "\n"
        "import aura_worker\n"
        "try:\n"
        "    aura_worker.launch_interactive_node\n"
        "except ImportError as exc:\n"
        "    print('raised:', exc)\n"
        "else:\n"
        "    print('no error')"
    )
    assert result.returncode == 0, result.stderr
    assert "aura-worker[ui]" in result.stdout


def test_unknown_attribute_still_raises_attribute_error():
    """The lazy hook must not turn typos into ImportErrors."""
    result = run_python(
        "import aura_worker\n"
        "try:\n"
        "    aura_worker.no_such_thing\n"
        "except AttributeError as exc:\n"
        "    print('raised:', exc)"
    )
    assert result.returncode == 0, result.stderr
    assert "no_such_thing" in result.stdout


def test_launch_interactive_node_still_resolves_when_the_ui_stack_is_installed():
    pytest.importorskip("gradio", reason="the [ui] extra is not installed")
    result = run_python(
        "import aura_worker\n"
        "assert callable(aura_worker.launch_interactive_node)\n"
        "print('resolved')"
    )
    assert result.returncode == 0, result.stderr
    assert "resolved" in result.stdout
