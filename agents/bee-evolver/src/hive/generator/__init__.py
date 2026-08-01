import subprocess  # nosec
from pathlib import Path

import structlog

from config import EvolverSettings
from ..utils import find_hive_root
from ..models import EvolutionPlan, Improvement

logger = structlog.get_logger(__name__)


class EvolverGenerator:
    """G - Generator: Applies improvements to the codebase and pushes a branch."""

    def __init__(self, settings: EvolverSettings) -> None:
        self.settings = settings
        self._root: Path = find_hive_root()

    def prepare_branch(self, timestamp: str) -> str:
        """Create and checkout a new evolver branch. Returns branch name.

        Uses -B (force-reset) so a previously interrupted cycle on the same
        timestamp doesn't cause a 'branch already exists' failure.
        """
        branch = f"evolver/cycle-{timestamp}"
        try:
            self._git(["checkout", "-B", branch])
            logger.info("evolver_branch_created", branch=branch)
        except Exception as e:
            logger.error("branch_creation_failed", branch=branch, error=str(e))
            raise
        return branch

    def apply_improvements(self, plan: EvolutionPlan) -> list[str]:
        """
        Apply all patchable improvements (code/prompt/doc) to the working tree.
        Returns list of error messages for improvements that could not be applied.
        """
        errors: list[str] = []
        for imp in plan.improvements:
            if imp.type in ("code", "prompt", "doc") and imp.patch:
                err = self._apply_patch(imp)
                if err:
                    errors.append(err)
        return errors

    def commit_and_push(self, branch: str, timestamp: str) -> bool:
        """Stage all changes, commit, and push the branch. Returns True on success."""
        try:
            status = self._git(["status", "--porcelain"])
            if not status.strip():
                logger.info("no_changes_to_commit")
                return True

            self._git(["add", "-A"])
            msg = (
                f"feat(evolver): autonomous improvement cycle {timestamp} [skip ci]\n\n"
                "Co-authored-by: bee.Evolver <evolver@aura.hive>"
            )
            self._git(["commit", "-m", msg])
            self._git(["push", "--set-upstream", "origin", branch])
            logger.info("evolver_branch_pushed", branch=branch)
            return True
        except Exception as e:
            logger.error("commit_push_failed", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_patch(self, imp: Improvement) -> str | None:
        """
        Apply a single improvement's patch.
        For prompt/doc types with a target_file, write the patch as full file content.
        For code type, attempt `git apply` with the unified diff.
        Returns an error string on failure, None on success.
        """
        assert imp.patch is not None  # caller guarantees this

        if imp.type in ("prompt", "doc") and imp.target_file:
            target = self._root / imp.target_file
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(imp.patch)
                logger.info("patch_written", file=imp.target_file, type=imp.type)
                return None
            except Exception as e:
                msg = f"Failed to write {imp.target_file}: {e}"
                logger.warning("patch_write_failed", file=imp.target_file, error=str(e))
                return msg

        if imp.type == "code":
            try:
                result = subprocess.run(  # nosec
                    ["git", "apply", "--check", "-"],
                    input=imp.patch,
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(self._root),
                )
                if result.returncode != 0:
                    msg = (
                        f"Patch for '{imp.title}' failed dry-run: "
                        f"{result.stderr.strip()[:200]}"
                    )
                    # git's stderr says exactly WHY the patch will not apply. It
                    # used to reach only the returned message, which the
                    # Connector reports — and dry-run short-circuits the
                    # Connector, so during baseline collection the reason was
                    # unobservable. The diff header goes with it: a wrong target
                    # path fails identically to a malformed hunk, and the two
                    # need different fixes.
                    logger.warning(
                        "patch_dry_run_failed",
                        title=imp.title,
                        target_file=imp.target_file,
                        error=result.stderr.strip()[:300],
                        patch_header=" | ".join(imp.patch.splitlines()[:4]),
                    )
                    return msg

                subprocess.run(  # nosec
                    ["git", "apply", "-"],
                    input=imp.patch,
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(self._root),
                )
                logger.info("code_patch_applied", title=imp.title)
                return None
            except subprocess.CalledProcessError as e:
                msg = f"git apply failed for '{imp.title}': {e.stderr[:200]}"
                logger.warning("code_patch_apply_failed", title=imp.title, error=str(e))
                return msg

        return None

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(  # nosec
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
            cwd=str(self._root),
        )
        return result.stdout
