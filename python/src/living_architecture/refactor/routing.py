"""Routing `dr-*` inputs by file language: own-language files run here, the other language's in its twin."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from living_architecture import twin
from living_architecture.config import ConfigError, find_repo_root, load_config, repo_languages
from living_architecture.contract import glob_match, language, language_ids, language_of, message


class RoutingError(Exception):
    """The inputs cannot be routed; the message is printed, exit 2."""


def _declaration(path: str, lang_id: str) -> bool:
    return any(glob_match(glob, PurePosixPath(path).as_posix()) for glob in language(lang_id)["declaration_globs"])


def _expansion_languages(root: Path) -> list[str]:
    try:
        config = load_config(root)
    except ConfigError as exc:
        raise RoutingError(str(exc)) from exc
    return repo_languages(root, config) or language_ids()


def _expand(directory: Path, languages: list[str]) -> list[tuple[str, str]]:
    """(language, path) of each file under `directory` the languages check, in path order."""
    out = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        lang_id = language_of(path.name)
        if lang_id not in languages or _declaration(str(path), lang_id):
            continue
        if set(path.relative_to(directory).parts[:-1]) & set(language(lang_id)["excluded_dirs"]):
            continue
        out.append((lang_id, str(path)))
    return out


def split(prog: str, raw_paths: list[str], cwd: Path) -> dict[str, list[str]]:
    """Paths grouped by language; directories expanded, non-source files skipped with a warning."""
    groups: dict[str, list[str]] = {}
    languages: list[str] | None = None
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            languages = _expansion_languages(find_repo_root(cwd)) if languages is None else languages
            for lang_id, file in _expand(path, languages):
                groups.setdefault(lang_id, []).append(file)
            continue
        lang_id = language_of(raw)
        if lang_id is None or _declaration(raw, lang_id):
            print(message("refactor.skipped", prog=prog, path=str(path)), file=sys.stderr)
            continue
        groups.setdefault(lang_id, []).append(str(path))
    return groups


def run_split(
    prog: str, groups: dict[str, list[str]], other_args: Callable[[list[str]], list[str]], native: Callable[[list[str]], int]
) -> int:
    """The other language's block from its twin (captured first), then every block in registry order; exit max."""
    captured: dict[str, bytes] = {}
    codes: list[int] = []
    for lang_id in (lang_id for lang_id in language_ids() if lang_id in groups and lang_id != twin.NATIVE_LANGUAGE):
        try:
            code, out = twin.run_captured(prog, lang_id, other_args(groups[lang_id]), repo_root=find_repo_root(Path.cwd()))
        except twin.TwinError as exc:
            print(message("twin.error", prog=prog, error=str(exc)), file=sys.stderr)
            return 2
        if code not in (0, 1):
            return 2
        captured[lang_id] = out
        codes.append(code)
    for lang_id in (lang_id for lang_id in language_ids() if lang_id in groups):
        if lang_id == twin.NATIVE_LANGUAGE:
            codes.append(native(groups[lang_id]))
        else:
            sys.stdout.flush()
            sys.stdout.buffer.write(captured[lang_id])
            sys.stdout.buffer.flush()
    return max(codes, default=0)


def source_language(path: str) -> str | None:
    """A file's language by extension; a directory's is the first language with a source file under it."""
    directory = Path(path)
    if not directory.is_dir():
        return language_of(path)
    found = {language_of(p.name) for p in directory.rglob("*") if p.is_file()}
    return next((lang_id for lang_id in language_ids() if lang_id in found), None)


def refactor_language(args: Any) -> str:
    """The language `dr-refactor` runs in; RoutingError (exit 1) for an unsupported source or a cross-language dest."""
    source = args.module if args.subcommand == "move-module" else args.file
    lang_id = source_language(source)
    if lang_id is None:
        raise RoutingError(message("refactor.unsupported-extension", path=source))
    if args.subcommand == "move-symbol" and language_of(args.dest) != lang_id:
        raise RoutingError(message("refactor.cross-language-dest", dest=args.dest, language=lang_id))
    return lang_id


def route_refactor(argv: list[str], args: Any, native: Callable[[], int]) -> int:
    """`dr-refactor`: run natively, or hand the raw ARGV to the source language's twin."""
    try:
        lang_id = refactor_language(args)
    except RoutingError as exc:
        print(exc, file=sys.stderr)
        return 1
    if lang_id == twin.NATIVE_LANGUAGE:
        return native()
    try:
        return twin.forward("dr-refactor", lang_id, argv, repo_root=find_repo_root(Path.cwd()))
    except twin.TwinError as exc:
        print(message("twin.error", prog="dr-refactor", error=str(exc)), file=sys.stderr)
        return 2


def compliance_selection(select: str | None) -> set[str] | None:
    """The selected check ids (None: every check); RoutingError naming ids no language lists."""
    if select is None:
        return None
    selected = {c.strip() for c in select.split(",") if c.strip()}
    known = {check for lang_id in language_ids() for check in language(lang_id)["compliance_checks"]}
    unknown = selected - known
    if unknown:
        raise RoutingError(message("compliance.unknown-checks", checks=", ".join(sorted(unknown))))
    return selected
