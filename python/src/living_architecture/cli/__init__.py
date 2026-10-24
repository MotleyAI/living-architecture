"""Every command's entry point: parse argv per the shared manifest, check the repo format, dispatch to the handler."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from living_architecture import archcheck, c4, config, conventions, doctor, refactor, review, twin, typecheck
from living_architecture.cli.parser import parse
from living_architecture.contract import manifest


def _argv(argv: list[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _root(root: str | None) -> Path:
    return Path(root).resolve() if root else config.find_repo_root(Path.cwd())


def _checked_root(args: argparse.Namespace) -> Path:
    """The repo whose format a command checks: `--root`, else the git root of `--project`, else of the cwd."""
    root: str | None = getattr(args, "root", None)
    project: str | None = getattr(args, "project", None)
    return _root(root) if root or not project else config.find_repo_root(Path(project))


def _run(command: str, argv: list[str], handler: Callable[[argparse.Namespace], int]) -> int:
    """Parse `argv` (not for a passthrough command), check the repo format unless exempt, then run `handler`."""
    spec = manifest()[command]
    args = argparse.Namespace() if spec.get("passthrough") else parse(command, argv)
    if spec.get("format") != "exempt":
        problem = config.check_format(_checked_root(args))
        if problem is not None:
            print(problem, file=sys.stderr)
            return 2
    return handler(args)


def _config(args: argparse.Namespace) -> int:
    root = _root(args.root)
    return config.run_show(root) if args.subcommand == "show" else config.run_get(root, args.key)


def la_config(argv: list[str] | None = None) -> int:
    return _run("la-config", _argv(argv), _config)


def _doctor(args: argparse.Namespace) -> int:
    if args.twin:
        print(twin.identity())
        return 0
    return doctor.run(
        root=_root(args.root),
        expect=args.expect,
        plugin=args.plugin,
        print_hash=args.contract_hash,
        require_config=args.require_config,
    )


def la_doctor(argv: list[str] | None = None) -> int:
    return _run("la-doctor", _argv(argv), _doctor)


def _arch_check(args: argparse.Namespace) -> int:
    language = args.language or (twin.NATIVE_LANGUAGE if args.emit else None)
    return archcheck.run(_root(args.root), language=language, emit=args.emit, top_level=args.top_level)


def la_arch_check(argv: list[str] | None = None) -> int:
    return _run("la-arch-check", _argv(argv), _arch_check)


def la_arch_scaffold(argv: list[str] | None = None) -> int:
    return _run("la-arch-scaffold", _argv(argv), lambda args: archcheck.run_scaffold(_root(args.root)))


def la_arch_diagrams(argv: list[str] | None = None) -> int:
    return _run("la-arch-diagrams", _argv(argv), lambda args: c4.run(_root(args.root)))


def la_arch_migrate(argv: list[str] | None = None) -> int:
    return _run("la-arch-migrate", _argv(argv), lambda args: c4.run_migrate(_root(args.root)))


def _check_conventions(args: argparse.Namespace) -> int:
    if args.emit:
        return conventions.emit(args.language or twin.NATIVE_LANGUAGE, cwd=Path.cwd())
    return conventions.check_conventions(
        repo_root=config.find_repo_root(Path.cwd()),
        pr=args.pr,
        repo=args.repo,
        base=args.base,
        files=args.files,
        excludes=args.exclude,
        cap_pct=args.text_ratio_cap,
    )


def la_check_conventions(argv: list[str] | None = None) -> int:
    return _run("la-check-conventions", _argv(argv), _check_conventions)


def la_count_comments(argv: list[str] | None = None) -> int:
    raw = _argv(argv)
    return _run("la-count-comments", raw, lambda _args: conventions.count_comments(raw))


def la_typecheck(argv: list[str] | None = None) -> int:
    return _run(
        "la-typecheck",
        _argv(argv),
        lambda args: typecheck.run(cwd=Path.cwd(), write=args.write_baseline, language_id=args.language),
    )


def la_fetch_coderabbit_threads(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-coderabbit-threads", _argv(argv))


def la_reply_invalid_coderabbit(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-invalid-coderabbit", _argv(argv))


def la_reply_to_pr_thread(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-to-pr-thread", _argv(argv))


def la_fetch_failed_pr_checks(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-failed-pr-checks", _argv(argv))


def la_wait_for_reviews(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-wait-for-reviews", _argv(argv))


def la_pr_reviewers(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-pr-reviewers", _argv(argv))


def _refactor(raw: list[str], args: argparse.Namespace) -> int:
    return refactor.route_refactor(
        raw,
        args,
        lambda: refactor.run_refactor(project_root=args.project, command=args.subcommand, apply=args.apply, options=vars(args)),
    )


def dr_refactor(argv: list[str] | None = None) -> int:
    raw = _argv(argv)
    return _run("dr-refactor", raw, lambda args: _refactor(raw, args))


def dr_compliance(argv: list[str] | None = None) -> int:
    return _run(
        "dr-compliance", _argv(argv), lambda args: refactor.run_compliance(paths=args.paths, select=args.select, attr=args.attr)
    )


def dr_mock_lint(argv: list[str] | None = None) -> int:
    raw = _argv(argv)
    return _run("dr-mock-lint", raw, lambda _args: refactor.run_mock_lint(raw))
