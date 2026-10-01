"""Parsers built from the shared CLI manifest."""

import pytest

from living_architecture.cli.parser import build_parser, parse
from living_architecture.contract import manifest

PARSED = sorted(name for name, spec in manifest().items() if not spec.get("passthrough"))


@pytest.mark.parametrize("command", PARSED)
def test_help_exits_0(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser(command)
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    assert command in capsys.readouterr().out


@pytest.mark.parametrize("command", PARSED)
def test_unknown_option_is_a_usage_error(command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        parse(command, ["--no-such-option"])
    assert exc.value.code == 2


def test_repeatable_option_defaults_to_empty() -> None:
    args = parse("la-check-conventions", ["--base", "main"])
    assert args.files == []
    assert args.exclude == []


def test_repeatable_option_collects_in_order() -> None:
    assert parse("la-check-conventions", ["--file", "b.py", "--file", "a.py"]).files == ["b.py", "a.py"]


def test_store_false_flag() -> None:
    base = ["rename", "--file", "a.py", "--name", "f", "--new-name", "g"]
    assert parse("dr-refactor", base).in_hierarchy is True
    assert parse("dr-refactor", [*base, "--no-in-hierarchy"]).in_hierarchy is False


def test_double_dash_before_a_subcommand() -> None:
    args = parse("la-config", ["--", "get", "--odd-key"])
    assert (args.subcommand, args.key) == ("get", "--odd-key")


def test_double_dash_without_subcommands_keeps_positionals_in_place() -> None:
    assert parse("dr-compliance", ["--", "-a.py", "b.py"]).paths == ["-a.py", "b.py"]


def test_require_one_of() -> None:
    with pytest.raises(SystemExit) as exc:
        parse("la-check-conventions", ["--repo", "o/r"])
    assert exc.value.code == 2


def test_choices_enforced() -> None:
    with pytest.raises(SystemExit) as exc:
        parse("dr-refactor", ["rename", "--file", "a.py", "--new-name", "g", "--unsure", "maybe"])
    assert exc.value.code == 2
