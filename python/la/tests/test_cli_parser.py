"""Parsers built from both packages' CLI manifests."""

import importlib
from pathlib import Path

import pytest
import yaml

from living_architecture import conventions, review
from living_architecture.contract import manifest as la_manifest
from trmv.cli.trmv_mock_lint import trmv_mock_lint
from trmv.contract import manifest as trmv_manifest
from trmv.contract.parser import build_parser, parse

COMMANDS = {**trmv_manifest(), **la_manifest()}
PARSED = sorted(name for name, spec in COMMANDS.items() if not spec.get("passthrough"))
SHARED = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir()) / "shared"
CASES = [
    case
    for package in ("trmv", "la")
    for case in yaml.safe_load((SHARED / package / "vectors" / "cli.yaml").read_text(encoding="utf-8"))["cases"]
]


def _passthrough(case: dict) -> bool:
    return bool(COMMANDS[case["command"]].get("passthrough"))


def _id(case: dict) -> str:
    return f"{case['command']} {case['name']}"


@pytest.mark.parametrize("case", [c for c in CASES if not _passthrough(c)], ids=_id)
def test_parser_vector(case: dict) -> None:
    if "exit" in case:
        with pytest.raises(SystemExit) as exc:
            parse(case["command"], case["argv"], COMMANDS)
        assert exc.value.code == case["exit"]
    else:
        assert vars(parse(case["command"], case["argv"], COMMANDS)) == case["args"]


@pytest.mark.parametrize("case", [c for c in CASES if _passthrough(c)], ids=_id)
def test_passthrough_vector(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[list[str]] = []
    monkeypatch.setattr(conventions, "count_comments", lambda argv: received.append(argv) or 0)
    monkeypatch.setattr(review, "run_shim", lambda _command, argv: received.append(argv))
    name = case["command"].replace("-", "_")
    getattr(importlib.import_module(f"living_architecture.cli.{name}"), name)(list(case["argv"]))
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
    parse(command, argv, COMMANDS)
    parser = build_parser(command, COMMANDS)
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    out = capsys.readouterr().out
    assert [name for name in hidden if name in out] == []


@pytest.mark.parametrize("command", PARSED)
def test_help_exits_0(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser(command, COMMANDS)
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    assert command in capsys.readouterr().out


@pytest.mark.parametrize("command", PARSED)
def test_unknown_option_is_a_usage_error(command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        parse(command, ["--no-such-option"], COMMANDS)
    assert exc.value.code == 2


def test_repeatable_option_defaults_to_empty() -> None:
    args = parse("la-check-conventions", ["--base", "main"], COMMANDS)
    assert args.files == []
    assert args.exclude == []


def test_repeatable_option_collects_in_order() -> None:
    assert parse("la-check-conventions", ["--file", "b.py", "--file", "a.py"], COMMANDS).files == ["b.py", "a.py"]


def test_store_false_flag() -> None:
    base = ["rename", "--file", "a.py", "--symbol", "f", "--new-name", "g"]
    assert parse("trmv-refactor", base, COMMANDS).in_hierarchy is True
    assert parse("trmv-refactor", [*base, "--no-in-hierarchy"], COMMANDS).in_hierarchy is False


def test_double_dash_before_a_subcommand() -> None:
    args = parse("la-config", ["--", "get", "--odd-key"], COMMANDS)
    assert (args.subcommand, args.key) == ("get", "--odd-key")


def test_double_dash_without_subcommands_keeps_positionals_in_place() -> None:
    assert parse("trmv-compliance", ["--", "-a.py", "b.py"], COMMANDS).paths == ["-a.py", "b.py"]


def test_require_one_of() -> None:
    with pytest.raises(SystemExit) as exc:
        parse("la-check-conventions", ["--repo", "o/r"], COMMANDS)
    assert exc.value.code == 2


@pytest.mark.parametrize("required", [["rename", "--new-name", "g"], ["move-symbol", "--dest", "b.py"],
                                      ["retarget", "--target", "g"]], ids=["rename", "move-symbol", "retarget"])
def test_exclusive_locators_name_both_options(required: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    argv = [required[0], "--file", "a.py", "--offset", "0", "--symbol", "f", *required[1:]]
    with pytest.raises(SystemExit) as exc:
        parse("trmv-refactor", argv, COMMANDS)
    assert exc.value.code == 2
    assert "argument --symbol: not allowed with argument --offset" in capsys.readouterr().err


def test_mock_lint_help_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        trmv_mock_lint(["--help"])
    assert exc.value.code == 0
    out, err = capsys.readouterr()
    assert "trmv-mock-lint" in out
    assert "--base" in out
    assert err == ""


def test_choices_enforced() -> None:
    with pytest.raises(SystemExit) as exc:
        parse("trmv-refactor", ["rename", "--file", "a.py", "--new-name", "g", "--unsure", "maybe"], COMMANDS)
    assert exc.value.code == 2
