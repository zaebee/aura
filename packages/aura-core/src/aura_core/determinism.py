"""
The Determinism Rule: non-determinism belongs to the Transformer alone.

Every other nucleotide — Aggregator, Connector, Generator, Membrane — must be
resultant or functional. Given the same context it must produce the same
decision, every time. A guarantee that can vary between runs is not a
guarantee, so entropy leaking into the Membrane silently voids it.

Deliberately NOT treated as entropy: uuid4, datetime.now, time.time and the
secrets module. The Pollen envelope requires an event id and a timestamp, and
Ed25519 signing requires cryptographic randomness. Those are load-bearing.

This module is pure: standard library only, no I/O, no project imports.
"""

import re
from collections.abc import Iterator, Sequence

# Model invocation. A bare mention is not a call site: the library name has to
# be imported, or be the receiver of an attribute access. Prose that merely
# names `litellm` inside a docstring reads as prose, including the prose above.
_LLM_LIBS = "litellm|dspy|openai|mistralai|anthropic"
LLM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        rf"(?:^|[^\w.])(?:import|from)\s+(?:{_LLM_LIBS})\b",
        rf"(?:^|[^\w.\"'`]) ?\b(?:{_LLM_LIBS})\s*\.\s*\w",
        r"\.chat\.completions\s*\.",
        r"\bChatCompletion\s*\(",
    )
)

# Statistical randomness. Distinct from cryptographic or identity entropy.
ENTROPY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bnp\.random\b",
        r"\bnumpy\.random\b",
        r"(?:^|[^\w.])import\s+random\b",
        r"(?:^|[^\w.])from\s+random\s+import\b",
        r"(?:^|[^\w.])from\s+numpy\s+import\s+random\b",
        # Any attribute on the module, not a list of names: `random` exposes 27
        # public callables and an enumeration was missing 16 of them, including
        # getrandbits, randbytes, SystemRandom and Random. The leading class
        # keeps `self.random.foo` and `np.random` out of this branch.
        r"(?:^|[^\w.])random\.\w",
    )
)

_COMMENT_PREFIXES = ("#", '"""', "'''", "*", "//")


def path_matches_prefix(file_path: str, prefix: str) -> bool:
    """
    True when file_path is the prefix itself, or sits beneath it.

    Plain startswith would let `membrane_bypass.py` match a `membrane` prefix —
    exactly the name someone trying to slip past a guard would reach for.
    """
    normalised = file_path.replace("\\", "/")
    prefix = prefix.replace("\\", "/").rstrip("/")
    return normalised == prefix or normalised.startswith(prefix + "/")


def is_python_source(file_path: str) -> bool:
    """
    True for Python source, excluding test modules.

    A lockfile, a pyproject or a workflow yaml may name `litellm` without ever
    invoking it, and test modules legitimately patch and mock model clients.
    """
    normalised = file_path.replace("\\", "/")
    if not normalised.endswith(".py"):
        return False
    if "/tests/" in normalised or normalised.startswith("tests/"):
        return False
    name = normalised.rsplit("/", 1)[-1]
    return not (name.startswith("test_") or name.endswith("_test.py"))


def is_transformer_path(file_path: str) -> bool:
    """True if the path belongs to a Transformer, where non-determinism lives."""
    normalised = file_path.replace("\\", "/")
    return (
        "/transformer/" in normalised
        or normalised.startswith("transformer/")
        or normalised.endswith("/transformer.py")
        or normalised == "transformer.py"
    )


def is_exempt(file_path: str, exempt_paths: Sequence[str]) -> bool:
    """True if the path is a Transformer or sits under a declared exempt prefix."""
    if is_transformer_path(file_path):
        return True
    return any(path_matches_prefix(file_path, prefix) for prefix in exempt_paths)


def check_determinism(
    file_path: str, added_line: str, exempt_paths: Sequence[str] = ()
) -> str | None:
    """
    Inspect one added line of a diff. Return a heresy message, or None if clean.

    Non-Python files, test modules, comments and blank lines are ignored, so a
    lockfile that merely names a model library does not read as a call site.
    """
    code = added_line.strip()
    if not code or code.startswith(_COMMENT_PREFIXES):
        return None
    if not is_python_source(file_path):
        return None
    if is_exempt(file_path, exempt_paths):
        return None

    for pattern in LLM_PATTERNS:
        match = pattern.search(code)
        if match:
            return (
                f"Determinism Heresy: model invocation `{match.group(0)}` added in "
                f"`{file_path}`, outside a Transformer: `{code}`. Reasoning belongs "
                f"to T alone; call it through the skill registry, or declare the "
                f"path in `determinism_exempt_paths`."
            )

    for pattern in ENTROPY_PATTERNS:
        match = pattern.search(code)
        if match:
            return (
                f"Determinism Heresy: statistical randomness `{match.group(0)}` added in "
                f"`{file_path}`, outside a Transformer: `{code}`. A nucleotide that "
                f"varies between runs cannot carry a guarantee."
            )

    return None


def iter_added_lines(diff: str) -> Iterator[tuple[str, str]]:
    """
        Walk a unified diff, yielding (file_path, added_line) for every added line.

    Header lines are only recognised outside a hunk. Inside one, `--- ` and
        `+++ ` are content: a deleted source line `-- x` renders as `--- x` and an
        added `++ y` as `+++ y`, so matching them as headers would reset the file
        path to garbage and drop the added line without a trace. Hunk boundaries
        come from `@@ ` and `diff --git `. Deleted files are ignored: `+++
        /dev/null` marks a removal, and a rule has nothing to say about code that
        is going away.
    """
    current = ""
    after_old_header = False
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            after_old_header = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk and line.startswith("--- "):
            after_old_header = True
            continue
        if not in_hunk and after_old_header and line.startswith("+++ "):
            after_old_header = False
            target = line[4:].strip()
            current = "" if target == "/dev/null" else target.removeprefix("b/")
            continue
        after_old_header = False
        if current and line.startswith("+"):
            yield current, line[1:]


def iter_changed_files(diff: str) -> set[str]:
    """
    Every file a unified diff touches — added to, modified, or deleted.

    `iter_added_lines` only reports files that gained a line, which is not the
    same question. Removing a guard is a change to it, and a rule that only
    watches additions would let an automated author delete the thing checking
    it. Header prefixes are stripped when present rather than required, so this
    survives `diff.noprefix` and custom --src-prefix/--dst-prefix.
    """
    files: set[str] = set()
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if in_hunk or not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        target = line[4:].strip()
        if target == "/dev/null":
            continue
        if target.startswith(("a/", "b/")):
            target = target[2:]
        if target:
            files.add(target)
    return files
