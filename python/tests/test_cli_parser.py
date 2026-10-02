"""Parsers built from the shared CLI manifest."""

from pathlib import Path

import pytest
import yaml

from living_architecture import cli, conventions, refactor, review
from living_architecture.cli.parser import build_parser, parse
from living_architecture.contract import manifest

PARSED = sorted(name for name, spec in manifest().items() if not spec.get("passthrough"))
VECTORS = next(p for p in Path(__file__).resolve().parents if (p / "shared" / "vectors").is_dir()) / "shared" / "vectors"
CASES = yaml.safe_load((VECTORS / "cli.yaml").read_text(encoding="utf-8"))["cases"]


def _passthrough(case: dict) -> bool:
    return bool(manifest()[case["command"]].get("passthrough"))


def _id(case: dict) -> str:
    return f"{case['command']} {case['name']}"


@pytest.mark.parametrize("case", [c for c in CASES if not _passthrough(c)], ids=_id)
def test_parser_vector(case: dict) -> None:
    if "exit" in case:
        with pytest.raises(SystemExit) as exc:
            parse(case["command"], case["argv"])
        assert exc.value.code == case["exit"]
    else:
        assert vars(parse(case["command"], case["argv"])) == case["args"]


@pytest.mark.parametrize("case", [c for c in CASES if _passthrough(c)], ids=_id)
def test_passthrough_vector(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[list[str]] = []
    monkeypatch.setattr(conventions, "count_comments", lambda argv: received.append(argv) or 0)
    monkeypatch.setattr(refactor, "run_mock_lint", lambda argv: received.append(argv) or 0)
    monkeypatch.setattr(review, "run_shim", lambda _command, argv: received.append(argv))
    getattr(cli, case["command"].replace("-", "_"))(list(case["argv"]))
    assert received == [case["args"]["argv"]]


@pytest.mark.parametrize(
    ("command", "argv", "hidden"),
    [
        ("la-doctor", ["--twin"], ["--twin"]),
        ("la-arch-check", ["--language", "python", "--emit", "facts"], ["--language", "--emit"]),
    ],
)
def test_internal_options_accepted_but_hidden(
    command: str, argv: list[str], hidden: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    parse(command, argv)
    parser = build_parser(command)
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    out = capsys.readouterr().out
    assert [name for name in hidden if name in out] == []


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
