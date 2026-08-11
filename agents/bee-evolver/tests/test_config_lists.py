"""
`EVOLVER_EXCLUDE_DIRS` accepts what its comment promises.

The field is `list[str]`, and pydantic-settings parses env values for those as
JSON. The comment beside it said comma-separated, so an operator following it
got a service that would not start — and an error naming JSON parsing rather
than the comment that misled them.

Comma-separated is the right format to accept for a list of directory names:
nobody wants to write a JSON array in a shell, and every other comma-separated
setting in this repo (the gateway's CORS and trusted-origin lists) is spelled
that way too. Doing the split in a validator rather than at each use keeps the
field properly typed and puts the parsing in one place.
"""

import os
from collections.abc import Iterator

import pytest
from config import EvolverSettings

DEFAULTS = [".git", ".venv", "node_modules", "__pycache__"]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    The variable under test removed, and the settings this model requires
    supplied.

    `EvolverSettings` declares two fields with no default — `llm__api_key` and
    `github_repository` — so constructing it needs both from the environment.
    Other modules in this directory set them at import time, which made an
    earlier version of this file pass in a full run and fail on its own: green
    only because of the order pytest happened to collect in. Supplied here so
    these tests stand up alone.
    """
    monkeypatch.delenv("EVOLVER_EXCLUDE_DIRS", raising=False)
    monkeypatch.setenv("AURA_LLM__API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_REPOSITORY", "zaebee/aura")
    yield


def with_value(value: str) -> list[str]:
    os.environ["EVOLVER_EXCLUDE_DIRS"] = value
    try:
        return EvolverSettings().exclude_dirs
    finally:
        os.environ.pop("EVOLVER_EXCLUDE_DIRS", None)


class TestTheDocumentedFormatWorks:
    def test_a_comma_separated_list_is_accepted(self, clean_env: None) -> None:
        """The format the comment promised, which used to fail at startup."""
        assert with_value(".git,.venv") == [".git", ".venv"]

    def test_spaces_around_entries_are_trimmed(self, clean_env: None) -> None:
        """`FOO=.git, .venv` is what a person writes; a leading space is not a name."""
        assert with_value(".git, .venv , node_modules") == [
            ".git",
            ".venv",
            "node_modules",
        ]

    def test_a_single_entry_needs_no_comma(self, clean_env: None) -> None:
        assert with_value(".git") == [".git"]

    def test_empty_entries_are_dropped(self, clean_env: None) -> None:
        """A trailing comma is a typo, not a directory named ''."""
        assert with_value(".git,,.venv,") == [".git", ".venv"]

    def test_an_empty_value_excludes_nothing(self, clean_env: None) -> None:
        """
        Distinct from the variable being unset, which keeps the defaults.
        Setting it to empty is a deliberate "scan everything".
        """
        assert with_value("") == []


class TestNothingElseBreaks:
    def test_the_json_form_still_works(self, clean_env: None) -> None:
        """
        Anything already deployed with a JSON array keeps working — the format
        that used to be the only one accepted.
        """
        assert with_value('[".git", ".venv"]') == [".git", ".venv"]

    def test_an_unset_variable_keeps_the_defaults(self, clean_env: None) -> None:
        settings = EvolverSettings()

        for expected in DEFAULTS:
            assert expected in settings.exclude_dirs


class TestABracketIsNotAlwaysJson:
    """
    `[` starts a JSON array and is also a legal first character for a directory
    name. Guessing by the bracket alone and calling `json.loads` on the result
    turns `[archived]` into a crash at startup — the same failure this whole
    change exists to remove, reintroduced one branch over.

    Falling back to comma-splitting is safe here in a way it would not be
    everywhere: this is an *exclude* list, so a misparsed entry names a
    directory that does not exist and excludes nothing. Failing open costs a
    wrong entry; failing closed costs the deployment.
    """

    def test_a_directory_named_like_an_array_is_not_json(self, clean_env: None) -> None:
        assert with_value("[archived]") == ["[archived]"]

    def test_such_a_name_inside_a_comma_separated_list(self, clean_env: None) -> None:
        assert with_value("[archived],.git") == ["[archived]", ".git"]

    def test_a_real_array_is_still_read_as_json(self, clean_env: None) -> None:
        """The fallback must not swallow the format it is there to preserve."""
        assert with_value('[".git", ".venv"]') == [".git", ".venv"]

    def test_a_malformed_array_does_not_take_the_service_down(
        self, clean_env: None
    ) -> None:
        """
        Entries come out odd, and that is the right trade: they name
        directories that do not exist, so nothing is excluded that should not
        be. Refusing to start would be worse for a list of things to skip.
        """
        result = with_value('[".git", ".venv"')

        assert isinstance(result, list)
