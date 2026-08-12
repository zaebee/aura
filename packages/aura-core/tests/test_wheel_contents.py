"""Packaging guard for aura-core: the wheel must ship the generated DNA.

`gen_hooks.py` transcribes proto/ into gen-proto/aura_core_gen at build time, and
pyproject lists that directory under [tool.hatch.build.targets.wheel] packages.
But gen-proto/ is VCS-ignored (.gitignore), and hatchling honours VCS ignore
rules during file selection — so without an explicit force_include the generated
modules are dropped from the wheel while the build stays green.

Nothing in the workspace notices: the dev tree has gen-proto/ on disk and installs
aura-core editable. Only a clean install from git (the Colab worker) finds out, at
`from aura_core_gen.aura.core.v1 import SystemVitals` in dna.py.

Both build contexts have to be exercised, because they fail in opposite ways:

- in the repo checkout the ignore rules apply, and only force_include gets the
  generated modules in — so this build must run *in place*, since a copy to a
  temp dir would leave .gitignore behind and let the bug pass unnoticed;
- in a Docker build context there is no VCS at all, nothing is ignored, and any
  mechanism that also selects gen-proto/ collides with force_include on the
  identical path.
"""

import shutil
import subprocess  # nosec B404
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel_contents(tmp_path_factory) -> list[str]:
    """Build the wheel as released and return the names it carries."""
    if not shutil.which("uv"):
        pytest.skip("uv is required to build the wheel")

    out_dir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(  # nosec B603 B607
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"wheel build failed:\n{result.stderr}"

    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as zf:
        return zf.namelist()


@pytest.fixture(scope="module")
def wheel_contents_without_vcs(tmp_path_factory) -> list[str]:
    """Build the way the Dockerfiles do: a copy of the tree, with no VCS in it.

    `uv sync` inside a Docker build context builds aura-core from a plain
    directory. Nothing is ignored there, so every include mechanism sees
    gen-proto/ — and two of them adding it means a duplicate-path build error.
    """
    if not shutil.which("uv"):
        pytest.skip("uv is required to build the wheel")

    context = tmp_path_factory.mktemp("context") / "aura-core"
    # symlinks=False resolves the proto/ symlink into real files, exactly as
    # `docker build` materialises the context it is given.
    shutil.copytree(PACKAGE_ROOT, context, symlinks=False)

    out_dir = tmp_path_factory.mktemp("dist-no-vcs")
    result = subprocess.run(  # nosec B603 B607
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=context,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"wheel build failed:\n{result.stderr}"

    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as zf:
        return zf.namelist()


def test_wheel_ships_generated_dna_package(wheel_contents):
    generated = [n for n in wheel_contents if n.startswith("aura_core_gen/")]
    assert generated, (
        "wheel carries no aura_core_gen/ — the build hook's output was dropped "
        "during file selection; importing aura_core would fail on a clean install"
    )


def test_wheel_ships_the_core_chromosome(wheel_contents):
    """dna.py imports SystemVitals from here at module scope."""
    assert "aura_core_gen/aura/core/v1.py" in wheel_contents


def test_wheel_ships_every_chromosome(wheel_contents):
    for chromosome in ("assets", "core", "dna", "knowledge", "negotiation"):
        assert f"aura_core_gen/aura/{chromosome}/v1.py" in wheel_contents


def test_wheel_ships_hand_written_source(wheel_contents):
    """The guard must fail on a missing genome, not on an empty wheel."""
    assert "aura_core/dna.py" in wheel_contents


def test_wheel_builds_outside_a_checkout(wheel_contents_without_vcs):
    """The Dockerfiles build from a context with no .gitignore to hold anything
    back — the wheel must still assemble, and still carry both halves."""
    assert "aura_core/dna.py" in wheel_contents_without_vcs
    assert "aura_core_gen/aura/core/v1.py" in wheel_contents_without_vcs
