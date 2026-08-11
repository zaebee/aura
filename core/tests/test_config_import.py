"""
Importing the Hive does not require a database URL.

`config/__init__.py` ended with `settings = get_settings()`, so merely importing
anything under `aura_hive` evaluated the whole settings tree — and
`DatabaseSettings.url` has no default. A module whose own imports are hashlib,
json and yaml could not be loaded without Postgres being configured.

That is not hypothetical tidiness. It failed a Docker build (#258): a one-line
check that the guard's rule set loads could not run, because the import chain
reached config and demanded credentials no build stage has. The workaround was
to load the module by path, which does not generalise.

These run in a subprocess with a scrubbed environment AND from a directory with
no `.env`. Both matter. `conftest.py` sets the required variables before
anything is imported, which is exactly the crutch this removes; and
`SettingsConfigDict(env_file=".env")` means a run from the repo root reads the
developer's own file. The first version of this test passed for that reason
while proving nothing — a build stage has neither.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
CORE_PATHS = os.pathsep.join(
    str(_REPO / p)
    for p in (
        "core/src",
        "core/gen-proto",
        "packages/aura-core/src",
        "packages/aura-core/gen-proto",
    )
)


def import_without_config(statement: str, cwd: Path) -> subprocess.CompletedProcess:
    """
    Run one import in a fresh interpreter with no AURA_ variables, from a
    directory carrying no `.env` — the conditions a Docker build stage has.
    """
    # Filtered rather than replaced. A hand-built environment strips whatever
    # the interpreter needs to start on someone else's machine, and this test
    # would then fail for a reason that has nothing to do with what it asserts —
    # which is the failure it exists to catch, so it should not commit it.
    #
    # The two conditions that matter are here: no AURA_ variables, and a cwd
    # with no `.env` for `SettingsConfigDict(env_file=".env")` to find.
    env = {k: v for k, v in os.environ.items() if not k.startswith("AURA_")}
    env["PYTHONPATH"] = CORE_PATHS

    return subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=120,
    )


class TestTheHiveImportsWithoutRuntimeConfiguration:
    def test_the_guard_ruleset_loads_without_a_database(self, tmp_path: Path) -> None:
        """
        The case that failed the build. It reads a YAML file beside itself and
        needs nothing else.
        """
        result = import_without_config(
            "from aura_hive.hive.proteins.guard.ruleset import load_ruleset;"
            "print(load_ruleset().version_string)",
            cwd=tmp_path,
        )

        assert result.returncode == 0, result.stderr
        assert "guard/negotiation@" in result.stdout

    def test_importing_the_config_module_evaluates_nothing(
        self, tmp_path: Path
    ) -> None:
        """
        Defining the class and a memoised accessor is all an import should do.
        Reading the environment at import time makes every consumer of any
        module in this package a consumer of the deployment's configuration.
        """
        result = import_without_config("import aura_hive.config", cwd=tmp_path)

        assert result.returncode == 0, result.stderr

    def test_the_membrane_imports_without_a_database(self, tmp_path: Path) -> None:
        """Anything that wants to reflect on the Hive — tooling, docs, a REPL."""
        result = import_without_config(
            "import aura_hive.hive.membrane.receipt", cwd=tmp_path
        )

        assert result.returncode == 0, result.stderr

    def test_asking_for_settings_still_fails_loudly_when_unconfigured(
        self, tmp_path: Path
    ) -> None:
        """
        The check moves, it does not disappear. A deployment missing its
        database URL must still be told, at the point something actually needs
        one — not turned into a service that starts and fails later.
        """
        result = import_without_config(
            "from aura_hive.config import get_settings; get_settings()",
            cwd=tmp_path,
        )

        assert result.returncode != 0
        assert "url" in result.stderr.lower()

    def test_the_entrypoint_module_imports_without_a_database(
        self, tmp_path: Path
    ) -> None:
        """
        `NegotiationService` lives in `main.py`, so an import-time settings read
        there makes the service class untestable without a deployment behind it.

        The entrypoint still needs configuration to *run* — `serve()` reads
        settings first thing. Needing it to be *imported* is the part that
        buys nothing.
        """
        result = import_without_config("import aura_hive.main", cwd=tmp_path)

        assert result.returncode == 0, result.stderr
