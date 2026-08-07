"""
The Javana Law: non-determinism belongs to the Transformer alone.

Every other nucleotide — Aggregator, Connector, Generator, Membrane — must be
resultant or functional. Given the same context it must produce the same
decision, every time. A guarantee that can vary between runs is not a
guarantee, so entropy leaking into the Membrane silently voids it.

(The rule is named for the javana phase of the Abhidhamma's seventeen-moment
cognitive process: the single stage that is ethically determinate, surrounded
by stages that are purely automatic. The name is a label, nothing more.)

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
        r"\brandom\.(?:random|randint|randrange|choice|choices|shuffle|sample"
        r"|uniform|gauss|normalvariate|seed)\b",
    )
)

_COMMENT_PREFIXES = ("#", '"""', "'''", "*", "//")


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
    return not normalised.rsplit("/", 1)[-1].startswith("test_")


def is_transformer_path(file_path: str) -> bool:
    """True if the path belongs to a Transformer, where non-determinism lives."""
    normalised = file_path.replace("\\", "/")
    return "/transformer/" in normalised or normalised.endswith("/transformer.py")


def is_exempt(file_path: str, exempt_paths: Sequence[str]) -> bool:
    """True if the path is a Transformer or sits under a declared exempt prefix."""
    if is_transformer_path(file_path):
        return True
    normalised = file_path.replace("\\", "/")
    return any(normalised.startswith(prefix) for prefix in exempt_paths)


def check_javana(
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
                f"Javana Heresy: model invocation `{match.group(0)}` added in "
                f"`{file_path}`, outside a Transformer: `{code}`. Reasoning belongs "
                f"to T alone; call it through the skill registry, or declare the "
                f"path in `javana_exempt_paths`."
            )

    for pattern in ENTROPY_PATTERNS:
        match = pattern.search(code)
        if match:
            return (
                f"Javana Heresy: statistical randomness `{match.group(0)}` added in "
                f"`{file_path}`, outside a Transformer: `{code}`. A nucleotide that "
                f"varies between runs cannot carry a guarantee."
            )

    return None


def iter_added_lines(diff: str) -> Iterator[tuple[str, str]]:
    """
    Walk a unified diff, yielding (file_path, added_line) for every added line.

    Deleted files are skipped: `+++ /dev/null` marks a removal, and a rule has
    nothing to say about code that is going away.
    """
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = "" if target == "/dev/null" else target.removeprefix("b/")
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if current and line.startswith("+"):
            yield current, line[1:]
