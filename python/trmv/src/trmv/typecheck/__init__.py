"""`trmv-typecheck`: each applicable language's checker against its committed, only-shrinking baseline, or in stealth mode
against the checker's errors at the merge base."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from trmv import __version__, changes, lang, twin
from trmv.config import (
    ConfigError,
    TrmvConfig,
    find_repo_root,
    is_stealth,
    language_settings,
    load_config,
    repo_languages,
    stealth_dir,
)
from trmv.contract import language, message, os_error_text
from trmv.lang.baseline import Key, diagnostics, marked
from trmv.lang.realign import Entries, merged, realigned, rekeyed
from trmv.typecheck.cache import cache_key, fingerprints, read_entry, write_entry

__all__ = ["CommandError", "applicable", "cache_key", "combined_exit", "python_diagnostics", "resolve_argv", "run",
           "split_command"]

_PATCH_RESULT = "result.json"


class Stealth(BaseModel):
    """A stealth run: the raw `--base` to hand another twin, and the merge-base commit, once one is needed."""

    model_config = ConfigDict(frozen=True)

    base: str | None
    commit: str | None


class CommandError(Exception):
    """The checker cannot be run; the message is printed, exit 2. `kind` says how it failed: it could not start
    (`start`), exited with `code` and `stderr` (`exit`), or la refused its run (`error`)."""

    def __init__(self, error: str, *, kind: str = "start", code: int | None = None, stderr: str = "") -> None:
        super().__init__(error)
        self.error = error
        self.kind = kind
        self.code = code
        self.stderr = stderr


def split_command(text: str) -> list[str]:
    """POSIX shell words without expansion (shared/vectors/command-split.yaml); ValueError when malformed."""
    return shlex.split(text)


def combined_exit(codes: list[int]) -> int:
    return max(codes, default=0)


def _err(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _error(error: str) -> int:
    _err(message("typecheck.error", error=error))
    return 2


def _command(config: TrmvConfig, lang_id: str) -> str | None:
    return getattr(config.commands.typecheck, lang_id)


def applicable(root: Path, config: TrmvConfig) -> list[str]:
    """The repo languages whose typecheck command is not `null`."""
    return [lang_id for lang_id in repo_languages(root, language_settings(root)) if _command(config, lang_id) is not None]


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_argv(root: Path, lang_id: str, command: str) -> list[str]:
    """The command's words with its first one resolved: a path from the repo root, else local bin dir, then PATH."""
    try:
        words = split_command(command)
    except ValueError:
        words = []
    if not words:
        raise CommandError(message("typecheck.bad-command", language=lang_id, command=command))
    local_bin = language(lang_id)["local_bin"]
    if "/" in words[0]:
        found = str(root / words[0]) if _executable(root / words[0]) else None
    else:
        found = str(root / local_bin / words[0]) if _executable(root / local_bin / words[0]) else shutil.which(words[0])
    if found is None:
        raise CommandError(message("typecheck.not-found", language=lang_id, command=words[0], local_bin=local_bin))
    return [found, *words[1:]]


def _patch_failure(patch: lang.PyrightPatch | None, command: str, versions: list[str]) -> str | None:
    if patch is None:
        return message("typecheck.patch-not-applied", command=command)
    if patch.outcome == "unverified":
        return message("typecheck.patch-unverified", verified=", ".join(versions), version=patch.version)
    if patch.outcome == "mismatch":
        return message("typecheck.patch-mismatch", version=patch.version, count=patch.count)
    return None


def _restore(path: Path, content: bytes | None) -> None:
    if content is None:
        if path.exists():
            path.unlink()
    elif not path.exists() or path.read_bytes() != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _run_python(root: Path, command: str, argv: list[str], *, write: bool, extra: list[str] | None = None) -> int:
    baseline = root / language("python")["baseline_file"]
    try:
        before = baseline.read_bytes() if baseline.exists() else None
    except OSError as exc:
        return _error(os_error_text(exc, root))
    flag = [lang.BASEDPYRIGHT_WRITE_FLAG] if write else []
    versions: list[str] = language("python")["checker_patch_versions"]
    with tempfile.TemporaryDirectory(prefix="la-pyright-patch-") as tmp:
        result = Path(tmp) / _PATCH_RESULT
        env = lang.pyright_patch_env(os.environ, result=result, versions=versions)
        try:
            returncode = subprocess.run([*argv, *flag, *(extra or [])], cwd=root, env=env, check=False).returncode
        except OSError as exc:
            return _error(os_error_text(exc, root, argv[0]))
        patch = lang.read_pyright_patch(result)
    failure = _patch_failure(patch, command, versions)
    if failure is not None:
        _restore(baseline, before)
        _err(failure)
        return 2
    code = lang.basedpyright_exit(returncode, write=write)
    if write and code == 0:
        if not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(lang.empty_basedpyright_baseline(), encoding="utf-8")
        _err(message("typecheck.write", language="python", baseline=language("python")["baseline_file"]))
    return code


def _is_entry(entry: object) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("range"), dict)


def _baseline_files(raw: bytes) -> tuple[dict[str, Any], dict[str, Entries]] | None:
    """A basedpyright baseline's data and its entries by file key; None when malformed."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return None
    if not all(isinstance(entries, list) and all(_is_entry(e) for e in entries) for entries in files.values()):
        return None
    return data, files


def _changed_texts(root: Path, ref: str, keys: list[str], renames: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Each listed file that exists and was renamed or edited since `ref`, with its text now and at `ref`."""
    out: dict[str, tuple[str, str]] = {}
    for key in keys:
        rel = key.removeprefix("./")
        path = root / rel
        if not key.startswith("./") or not path.is_file():
            continue
        before = changes.file_at(ref=ref, path=renames.get(rel, rel), repo_root=root)
        now = path.read_bytes()
        if before is None or (rel not in renames and before == now):
            continue
        try:
            out[rel] = now.decode("utf-8"), before.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out


def _marked(root: Path, command: str, baseline: str, files: list[str]) -> list[tuple[str, Key, bool]]:
    """The diagnostics of `files` in report order, each with whether `baseline` hides it."""
    with tempfile.TemporaryDirectory(prefix="la-baseline-") as tmp:
        empty, copy = Path(tmp) / "empty.json", Path(tmp) / "copy.json"
        empty.write_text('{"files": {}}', encoding="utf-8")
        copy.write_text(baseline, encoding="utf-8")
        everything = diagnostics(python_diagnostics(root, command, ["--baselinefile", str(empty), *files]), root)
        shown = diagnostics(python_diagnostics(root, command, ["--baselinefile", str(copy), *files]), root)
    return marked(everything, shown)


def _since(root: Path, ref: str) -> tuple[str, dict[str, str]] | int:
    """The commit `ref` names and the renames since it; the exit code when git cannot tell."""
    try:
        commit = changes.commit_id(ref=ref, repo_root=root)
        if commit is None:
            _err(message("typecheck.bad-ref", ref=ref))
            return 2
        return commit, changes.base_paths(ref=commit, repo_root=root)
    except ConfigError as exc:
        return _error(str(exc))


def _probe_failed(exc: CommandError) -> int:
    if exc.kind == "exit":
        sys.stderr.write(exc.stderr)
        sys.stderr.flush()
    else:
        _err(str(exc))
    return 2


def _replaced(root: Path, baseline: Path, text: str) -> int | None:
    """Write `text` over the baseline (the file a link names), whole or not at all; the exit code when that fails."""
    target = baseline.resolve()
    try:
        handle, name = tempfile.mkstemp(prefix=f"{target.name}.", dir=target.parent)
    except OSError as exc:
        return _error(os_error_text(exc, root))
    temp = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        shutil.copymode(target, temp)
        os.replace(temp, target)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        return _error(os_error_text(exc, root))
    return None


def _realign_texts(texts: dict[str, tuple[str, str]], found: list[tuple[str, Key, bool]], listed: dict[str, Entries],
                   files: dict[str, Entries], renames: dict[str, str]) -> int:
    """Realign `files` in place to each changed file's errors now; how many entries of an unrenamed file moved."""
    count = 0
    for rel, (now, before) in texts.items():
        key = f"./{rel}"
        ours = [(k, hidden) for path, k, hidden in found if path == rel]
        if rel in renames and listed.get(key):
            files[key] = merged(listed[key], listed[f"./{renames[rel]}"], ours, now, before)
        entries = realigned(files[key], ours, now, before)
        if rel not in renames:
            count += sum(1 for old, new in zip(files[key], entries, strict=True) if old != new)
        files[key] = entries
    return count


def _realign(root: Path, command: str, ref: str, baseline: Path | None = None) -> int | None:
    """Move each Python baseline entry to where its error is now, given that the baseline matched at `ref`; the exit
    code when that fails. `baseline` (default: the committed one) given, the realignment is silent."""
    baseline_rel: str = language("python")["baseline_file"]
    quiet = baseline is not None
    baseline = baseline or root / baseline_rel
    if not baseline.is_file():
        return None
    parsed = _baseline_files(baseline.read_bytes())
    if parsed is None:
        _err(message("typecheck.baseline-invalid", language="python", baseline=baseline_rel))
        return 2
    data, listed = parsed
    since = _since(root, ref)
    if isinstance(since, int):
        return since
    commit, renames = since
    files = rekeyed(listed, renames)
    count = sum(len(listed.get(f"./{old}", [])) for old in renames.values())
    texts = _changed_texts(root, commit, list(files), renames)
    if texts:
        try:
            found = _marked(root, command, json.dumps({**data, "files": files}), sorted(texts))
        except CommandError as exc:
            return _probe_failed(exc)
        count += _realign_texts(texts, found, listed, files, renames)
    if not count:
        return None
    new_data = {**data, "files": {key: files[key] for key in sorted(files) if files[key]}}
    failed = _replaced(root, baseline, json.dumps(new_data, indent=4))
    if failed is None and not quiet:
        _err(message("typecheck.realign", language="python", count=count, baseline=baseline_rel, ref=ref))
    return failed


def _merge_base_failed(lang_id: str, command: str, commit: str) -> int:
    _err(message("typecheck.merge-base-failed", language=lang_id, command=command, commit=commit[:7]))
    return 2


def _python_checked_out(root: Path, command: str, commit: str) -> str | None:
    """The checker's Python baseline at `commit`, from a temporary checkout; None when the checker fails there."""
    versions: list[str] = language("python")["checker_patch_versions"]
    with lang.merge_base_checkout(root, commit, language("python")["environment_dirs"]) as checkout:
        try:
            argv = resolve_argv(checkout, "python", command)
        except CommandError:
            return None
        with tempfile.TemporaryDirectory(prefix="la-pyright-patch-") as tmp:
            result = Path(tmp) / _PATCH_RESULT
            env = lang.pyright_patch_env(os.environ, result=result, versions=versions)
            try:
                proc = subprocess.run([*argv, lang.BASEDPYRIGHT_WRITE_FLAG], cwd=checkout, env=env, capture_output=True,
                                      check=False)
            except OSError:
                return None
            patch = lang.read_pyright_patch(result)
        if _patch_failure(patch, command, versions) is not None or lang.basedpyright_exit(proc.returncode, write=True):
            return None
        written = checkout / language("python")["baseline_file"]
        return written.read_text(encoding="utf-8") if written.is_file() else lang.empty_basedpyright_baseline()


def _python_at(root: Path, command: str, commit: str) -> str | int:
    """The Python baseline of the checker's errors at `commit`, from the cache or a temporary checkout; the exit code
    when the checker fails there."""
    key = cache_key(commit=commit, language="python", command=command, version=__version__,
                    fingerprints=fingerprints(root, "python"))
    directory = stealth_dir(root, "trmv")
    entry = None if directory is None else directory / "typecheck" / f"{key}.json"
    cached = None if entry is None else read_entry(entry)
    if cached is not None and _baseline_files(cached.encode("utf-8")) is not None:
        return cached
    try:
        text = _python_checked_out(root, command, commit)
    except lang.CheckoutError:
        text = None
    if text is None or _baseline_files(text.encode("utf-8")) is None:
        return _merge_base_failed("python", command, commit)
    if entry is not None:
        write_entry(entry, text)
    return text


def _check_stealth_python(root: Path, command: str, argv: list[str], commit: str) -> int:
    """The working tree checked against the merge base's errors, realigned to it."""
    baseline = _python_at(root, command, commit)
    if isinstance(baseline, int):
        return baseline
    with tempfile.TemporaryDirectory(prefix="trmv-stealth-baseline-") as tmp:
        path = Path(tmp) / "baseline.json"
        path.write_text(baseline, encoding="utf-8")
        failed = _realign(root, command, commit, path)
        if failed is not None:
            return failed
        sys.stdout.flush()
        return _run_python(root, command, argv, write=False, extra=["--baselinefile", str(path)])


def python_diagnostics(root: Path, command: str, extra: list[str]) -> dict[str, object]:
    """The configured Python checker's `--outputjson` report with `extra` appended; CommandError when it fails."""
    argv = [word for word in resolve_argv(root, "python", command) if word not in lang.BASEDPYRIGHT_NOT_WITH_JSON]
    versions: list[str] = language("python")["checker_patch_versions"]
    with tempfile.TemporaryDirectory(prefix="la-pyright-patch-") as tmp:
        result = Path(tmp) / _PATCH_RESULT
        env = lang.pyright_patch_env(os.environ, result=result, versions=versions)
        try:
            proc = subprocess.run([*argv, "--outputjson", *extra], cwd=root, env=env, capture_output=True, check=False)
        except OSError as exc:
            raise CommandError(os_error_text(exc, root)) from None
        patch = lang.read_pyright_patch(result)
    stderr = proc.stderr.decode(errors="replace")
    failure = _patch_failure(patch, command, versions)
    # A refusal the preload recorded exits 2 without a word, so it comes before the exit code.
    if failure is not None and patch is not None:
        raise CommandError(failure, kind="error")
    if lang.basedpyright_exit(proc.returncode, write=False) == 2:
        raise CommandError(stderr, kind="exit", code=proc.returncode, stderr=stderr)
    if failure is not None:
        raise CommandError(failure, kind="error")
    no_report = CommandError(message("refactor.checker-no-report"), kind="error", stderr=stderr)
    # basedpyright prints a line before the report when it updates a baseline whose errors went down.
    lines = proc.stdout.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith(b"{")), 0)
    try:
        report = json.loads(b"".join(lines[start:]))
    except ValueError:
        raise no_report from None
    if not isinstance(report, dict):
        raise no_report
    return report


def _check_native(root: Path, command: str, *, write: bool, ref: str | None, stealth: Stealth | None) -> int:
    try:
        argv = resolve_argv(root, twin.NATIVE_LANGUAGE, command)
    except CommandError as exc:
        _err(str(exc))
        return 2
    baseline: str = language("python")["baseline_file"]
    if stealth is not None and not changes.tracked_at_head(path=baseline, repo_root=root):
        try:
            return _check_stealth_python(root, command, argv, stealth.commit or "")
        except OSError as exc:
            return _error(os_error_text(exc, root))
    if ref is not None:
        try:
            failed = _realign(root, command, ref)
        except OSError as exc:
            return _error(os_error_text(exc, root))
        if failed is not None:
            return failed
    sys.stdout.flush()
    code = _run_python(root, command, argv, write=write)
    if code == 1 and ref is None and not write and (root / baseline).is_file():
        _err(message("typecheck.realign-hint", language="python", baseline=baseline))
    return code


def _check(root: Path, lang_id: str, command: str, *, write: bool, ref: str | None, stealth: Stealth | None) -> int:
    if lang_id == twin.NATIVE_LANGUAGE:
        return _check_native(root, command, write=write, ref=ref, stealth=stealth)
    args = ["--write-baseline"] if write else []
    if stealth is not None and stealth.base is not None:
        args += ["--base", stealth.base]
    try:
        return twin.run_language("trmv-typecheck", lang_id, args, cwd=root, repo_root=root)
    except twin.TwinError as exc:
        return _error(str(exc))


def _setup(cwd: Path) -> tuple[Path, TrmvConfig] | int:
    root = find_repo_root(cwd)
    if not (root / ".git").exists():
        _err(message("typecheck.not-git"))
        return 2
    try:
        return root, load_config(root)
    except ConfigError as exc:
        return _error(str(exc))


def _check_only(root: Path, config: TrmvConfig, language_id: str, *, write: bool, ref: str | None,
                stealth: Stealth | None) -> int:
    if language_id != twin.NATIVE_LANGUAGE:
        return _error(message("typecheck.not-native", language=language_id))
    return _check_native(root, _command(config, language_id) or "", write=write, ref=ref, stealth=stealth)


def _check_all(root: Path, config: TrmvConfig, languages: list[str], *, write: bool, ref: str | None,
               stealth: Stealth | None) -> int:
    if not languages:
        _err(message("typecheck.no-languages"))
        return 0
    codes = []
    for lang_id in languages:
        command = _command(config, lang_id) or ""
        _err(message("typecheck.header", language=lang_id, command=command))
        baseline = language(lang_id)["baseline_file"]
        if write and (root / baseline).exists():
            _err(message("typecheck.skip", language=lang_id, baseline=baseline))
            continue
        codes.append(_check(root, lang_id, command, write=write, ref=ref, stealth=stealth))
    if write and not codes:
        _err(message("typecheck.refusal"))
        return 2
    return combined_exit(codes)


def _merge_base(root: Path, base: str | None) -> str | int:
    """The merge base of the base ref (`--base`, else origin/HEAD's target) and HEAD; the exit code when none."""
    try:
        ref = changes.resolve_base_ref(base=base, repo_root=root) if base is not None else changes.default_base_ref(root)
        if ref is None:
            _err(message("typecheck.stealth-no-base"))
            return 2
        return changes.merge_base(base_ref=ref, repo_root=root)
    except ConfigError as exc:
        return _error(str(exc))


def _stealth(root: Path, languages: list[str], *, write: bool, ref: str | None, base: str | None) -> Stealth | int | None:
    """The stealth run, None outside stealth mode; the exit code of a stealth refusal."""
    if not is_stealth(root):
        return None
    if write:
        _err(message("typecheck.stealth-write-refused"))
        return 2
    untracked = [lang_id for lang_id in languages
                 if not changes.tracked_at_head(path=language(lang_id)["baseline_file"], repo_root=root)]
    if ref is not None and not changes.tracked_at_head(path=language("python")["baseline_file"], repo_root=root):
        _err(message("typecheck.stealth-realign-refused"))
        return 2
    if not untracked:
        return Stealth(base=base, commit=None)
    commit = _merge_base(root, base)
    return commit if isinstance(commit, int) else Stealth(base=base, commit=commit)


def run(
    *, cwd: Path, write: bool, language_id: str | None, realign_from: str | None = None, base: str | None = None
) -> int:
    """`trmv-typecheck`; with `language_id` (the twins' protocol) only that native language, without a header. With
    `realign_from`, the Python baseline is realigned from that commit before its check; in stealth mode, `base` names
    the branch whose merge base gives the baseline of each language the repo tracks none for."""
    setup = _setup(cwd)
    if isinstance(setup, int):
        return setup
    root, config = setup
    try:
        known = realign_from is None or changes.is_commit(ref=realign_from, repo_root=root)
        languages = [language_id] if language_id is not None else applicable(root, config)
        stealth = _stealth(root, languages, write=write, ref=realign_from, base=base) if known else None
    except ConfigError as exc:
        return _error(str(exc))
    if not known:
        _err(message("typecheck.bad-ref", ref=realign_from))
        return 2
    if isinstance(stealth, int):
        return stealth
    if language_id is not None:
        return _check_only(root, config, language_id, write=write, ref=realign_from, stealth=stealth)
    return _check_all(root, config, languages, write=write, ref=realign_from, stealth=stealth)
