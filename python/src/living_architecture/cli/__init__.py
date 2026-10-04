"""Every command's entry point: parse argv per the shared manifest, dispatch to the owning node's handler."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NoReturn

from living_architecture import archcheck, c4, config, conventions, doctor, refactor, review, twin, typecheck
from living_architecture.cli.parser import parse


def _argv(argv: list[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _root(root: str | None) -> Path:
    return Path(root).resolve() if root else config.find_repo_root(Path.cwd())


def la_config(argv: list[str] | None = None) -> int:
    args = parse("la-config", _argv(argv))
    root = _root(args.root)
    return config.run_show(root) if args.subcommand == "show" else config.run_get(root, args.key)


def la_doctor(argv: list[str] | None = None) -> int:
    args = parse("la-doctor", _argv(argv))
    if args.twin:
        print(twin.identity())
        return 0
    return doctor.run(
        root=_root(args.root), expect=args.expect, print_hash=args.contract_hash, require_config=args.require_config
    )


def la_arch_check(argv: list[str] | None = None) -> int:
    args = parse("la-arch-check", _argv(argv))
    language = args.language or (twin.NATIVE_LANGUAGE if args.emit else None)
    return archcheck.run(_root(args.root), language=language, emit=args.emit, top_level=args.top_level)


def la_arch_scaffold(argv: list[str] | None = None) -> int:
    return archcheck.run_scaffold(_root(parse("la-arch-scaffold", _argv(argv)).root))


def la_arch_diagrams(argv: list[str] | None = None) -> int:
    return c4.run(_root(parse("la-arch-diagrams", _argv(argv)).root))


def la_check_conventions(argv: list[str] | None = None) -> int:
    args = parse("la-check-conventions", _argv(argv))
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


def la_count_comments(argv: list[str] | None = None) -> int:
    return conventions.count_comments(_argv(argv))


def la_typecheck(argv: list[str] | None = None) -> int:
    args = parse("la-typecheck", _argv(argv))
    return typecheck.run(cwd=Path.cwd(), write=args.write_baseline, language_id=args.language)


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


def dr_refactor(argv: list[str] | None = None) -> int:
    args = parse("dr-refactor", _argv(argv))
    return refactor.run_refactor(project_root=args.project, command=args.subcommand, apply=args.apply, options=vars(args))


def dr_compliance(argv: list[str] | None = None) -> int:
    args = parse("dr-compliance", _argv(argv))
    return refactor.run_compliance(paths=args.paths, select=args.select, attr=args.attr)


def dr_mock_lint(argv: list[str] | None = None) -> int:
    return refactor.run_mock_lint(_argv(argv))
