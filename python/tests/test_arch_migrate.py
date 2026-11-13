"""la-arch-migrate: all-or-nothing writes under injected filesystem failures, and the verification guard."""

from __future__ import annotations

import builtins
import io
import itertools
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

import pytest

from living_architecture import cli, config, contract
from living_architecture.c4 import migrate as c4_migrate

CASES = next(p for p in Path(__file__).resolve().parents if (p / "conformance").is_dir()) / "conformance" / "cases"

SPEC = "specification {\n  element system\n  element node\n}\n"
PYTHON = "model {\n  python = system 'Python' {\n    core = node 'Core'\n    db = node 'DB'\n    core -> db\n  }\n}\n"
VIEWS = "views {\n  view land of python {\n    include *\n  }\n}\n"
MISMATCH = "la-arch-migrate: the merged files would not parse to the same model and views; nothing written\n"
CONFIG = "living-architecture.yaml"
UNVERSIONED = "# repo config\ntracker: linear\n"
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def legacy_repo(tmp_path: Path, *, views: bool) -> Path:
    model = tmp_path / "repo" / "architecture" / "model"
    model.mkdir(parents=True)
    (model / "specification.c4").write_text(SPEC, encoding="utf-8")
    (model / "python.c4").write_text(PYTHON, encoding="utf-8")
    # Non-default modes, so a rollback that loses them changes the snapshot.
    for legacy in model.iterdir():
        legacy.chmod(0o600)
    model.chmod(0o700)
    (tmp_path / "repo" / "architecture" / "index.yaml").write_text("python:\n  root_package: pkg\n", encoding="utf-8")
    (tmp_path / "repo" / CONFIG).write_text(UNVERSIONED, encoding="utf-8")
    if views:
        (tmp_path / "repo" / "architecture" / "views.c4").write_text(VIEWS, encoding="utf-8")
    return tmp_path / "repo"


ARC42_PYTHON = PYTHON.replace(
    "    core = node 'Core'\n",
    "    core = node 'Core' {\n      metadata {\n        arc42 'architecture/core.arc42.md'\n      }\n    }\n",
)
ARC42_DONE = PYTHON.replace("    core = node 'Core'\n", "    core = node 'Core' {\n    }\n")
ARC42_INDEX = (
    "python:\n  root_package: pkg  # kept\n"
    "cross_cutting_arc42:\n- architecture/rules/rules.arc42.md\n"
    "diagrams:\n  architecture/core.arc42.md: [land]\n"
)
ARC42_REPORT = (
    "moved architecture/core.arc42.md to architecture/python.core.arc42.md\n"
    "moved architecture/rules/rules.arc42.md to architecture/rules.arc42.md\n"
)


def arc42_repo(tmp_path: Path, *, legacy: bool) -> Path:
    """A repo whose model sets an arc42 key and whose index lists a nested cross-cutting doc."""
    root = tmp_path / "repo"
    files = {
        "architecture/index.yaml": ARC42_INDEX,
        "architecture/views.c4": VIEWS,
        "architecture/core.arc42.md": "# Core\n",
        "architecture/rules/rules.arc42.md": "# Rules\n",
    }
    if legacy:
        files |= {"architecture/model/specification.c4": SPEC, "architecture/model/python.c4": ARC42_PYTHON}
    else:
        files["architecture/model.c4"] = SPEC + ARC42_PYTHON
    for rel, text in {**files, CONFIG: UNVERSIONED}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
        # Non-default modes, so a rollback that loses them changes the snapshot.
        (root / rel).chmod(0o600)
    return root


REPOS: dict[str, Callable[[Path], Path]] = {
    "views-created": lambda tmp: legacy_repo(tmp, views=False),
    "views-kept": lambda tmp: legacy_repo(tmp, views=True),
    "arc42-canonical": lambda tmp: arc42_repo(tmp, legacy=False),
    "arc42-legacy": lambda tmp: arc42_repo(tmp, legacy=True),
}


Snapshot = tuple[dict[str, int], dict[str, tuple[int, bytes]]]


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def snapshot(root: Path) -> Snapshot:
    """Every directory's mode and every file's mode and bytes under `root`."""
    dirs: dict[str, int] = {}
    files: dict[str, tuple[int, bytes]] = {}
    for here, subdirs, names in os.walk(root):
        dirs.update({os.path.relpath(Path(here) / d, root): _mode(Path(here) / d) for d in subdirs})
        files.update({os.path.relpath(Path(here) / n, root): (_mode(Path(here) / n), (Path(here) / n).read_bytes()) for n in names})
    return dirs, files


def changed_paths(before: Snapshot, after: Snapshot) -> set[str]:
    """The directories and files that differ between two snapshots."""
    dirs = before[0].keys() | after[0].keys()
    files = before[1].keys() | after[1].keys()
    return {rel for rel in dirs if before[0].get(rel) != after[0].get(rel)} | {
        rel for rel in files if before[1].get(rel) != after[1].get(rel)
    }


class Faults:
    """Records every filesystem mutation under `root` and fails the `fail_at`-th one (and every later one with `fail_from`).

    `after` makes a failing create happen first (the file exists, then the write fails).
    """

    def __init__(self, root: Path, fail_at: int | None = None, after: bool = False, fail_from: bool = False) -> None:
        self.root = str(root.resolve())
        self.fail_at = fail_at
        self.after = after
        self.fail_from = fail_from
        self.ops: list[tuple[str, str]] = []

    def _mine(self, path: Any) -> str | None:
        if isinstance(path, int):
            return None
        full = os.path.abspath(os.fspath(path))
        return full if full == self.root or full.startswith(self.root + os.sep) else None

    def _hit(self, op: str, path: str) -> bool:
        self.ops.append((op, os.path.relpath(path, self.root)))
        index = len(self.ops) - 1
        return self.fail_at is not None and (index >= self.fail_at if self.fail_from else index == self.fail_at)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_open, real_os_open = builtins.open, os.open

        def wrapped_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            path = self._mine(file)
            if path is None or not any(c in mode for c in "wxa+"):
                return real_open(file, mode, *args, **kwargs)
            if self._hit("open", path):
                if self.after:
                    real_open(file, mode, *args, **kwargs).close()
                raise OSError(f"injected failure: open {path}")
            return real_open(file, mode, *args, **kwargs)

        def wrapped_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            mine = self._mine(path)
            if mine is not None and flags & _WRITE_FLAGS and self._hit("open", mine):
                if self.after:
                    os.close(real_os_open(path, flags, *args, **kwargs))
                raise OSError(f"injected failure: open {mine}")
            return real_os_open(path, flags, *args, **kwargs)

        def guard(op: str, real: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(path: Any, *args: Any, **kwargs: Any) -> Any:
                mine = self._mine(path)
                if mine is not None and self._hit(op, mine):
                    raise OSError(f"injected failure: {op} {mine}")
                return real(path, *args, **kwargs)

            return wrapped

        monkeypatch.setattr(builtins, "open", wrapped_open)
        monkeypatch.setattr(io, "open", wrapped_open)
        monkeypatch.setattr(os, "open", wrapped_os_open)
        for name in ("unlink", "remove", "rmdir", "mkdir", "rename", "replace"):
            monkeypatch.setattr(os, name, guard(name, getattr(os, name)))


def migrate(root: Path) -> int:
    return cli.la_arch_migrate(["--root", str(root)])


@pytest.mark.parametrize("kind", list(REPOS))
def test_every_failed_mutation_leaves_the_repo_unchanged(tmp_path, monkeypatch, capsys, kind):
    make = REPOS[kind]
    probe = make(tmp_path / "probe")
    recorder = Faults(probe)
    with monkeypatch.context() as patch:
        recorder.install(patch)
        assert migrate(probe) == 0
    capsys.readouterr()
    assert recorder.ops, "the migration mutated nothing under the repo"
    if kind != "views-created":
        assert ("open", "architecture/views.c4") not in recorder.ops
    for fail_at, (op, path) in enumerate(recorder.ops):
        for after in (False, True) if op == "open" else (False,):
            repo = make(tmp_path / f"run-{fail_at}-{after}")
            before = snapshot(repo)
            with monkeypatch.context() as patch:
                Faults(repo, fail_at=fail_at, after=after).install(patch)
                code = migrate(repo)
            captured = capsys.readouterr()
            context = (fail_at, op, path, after)
            assert code == 2, context
            assert captured.out == "", context
            assert captured.err.startswith("la-arch-migrate: "), context
            assert snapshot(repo) == before, context


def _recorded_ops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str]]:
    probe = legacy_repo(tmp_path / "probe", views=False)
    recorder = Faults(probe)
    with monkeypatch.context() as patch:
        recorder.install(patch)
        assert migrate(probe) == 0
    capsys.readouterr()
    return recorder.ops


def test_the_config_is_replaced_last_from_a_sibling_temp_file(tmp_path, monkeypatch, capsys):
    ops = _recorded_ops(tmp_path, monkeypatch, capsys)
    op, path = ops[-1]
    assert op in ("rename", "replace"), ops
    assert (os.path.dirname(path), path == CONFIG) == ("", False), ops
    assert ("open", path) in ops[:-1], ops
    assert all(p != CONFIG for _, p in ops[:-1]), ops


def test_a_failed_restore_names_every_path_left_changed(tmp_path, monkeypatch, capsys):
    ops = _recorded_ops(tmp_path, monkeypatch, capsys)
    named_any = False
    for fail_at in range(len(ops)):
        repo = legacy_repo(tmp_path / f"run-{fail_at}", views=False)
        before = snapshot(repo)
        with monkeypatch.context() as patch:
            Faults(repo, fail_at=fail_at, fail_from=True).install(patch)
            code = migrate(repo)
        captured = capsys.readouterr()
        left = changed_paths(before, snapshot(repo))
        assert (code, captured.out) == (2, ""), (fail_at, captured)
        assert captured.err.startswith("la-arch-migrate: "), fail_at
        assert [rel for rel in sorted(left) if rel not in captured.err] == [], (fail_at, captured.err)
        assert ("left changed" in captured.err) is bool(left), (fail_at, captured.err)
        named_any = named_any or bool(left)
    assert named_any, "no failure point left a path changed"


def test_successful_migration_removes_the_emptied_model_directory(tmp_path, capsys):
    repo = legacy_repo(tmp_path, views=True)
    assert migrate(repo) == 0
    assert capsys.readouterr().out == (
        "wrote architecture/model.c4\n"
        "wrote living-architecture.yaml\n"
        "deleted architecture/model/python.c4\n"
        "deleted architecture/model/specification.c4\n"
        "deleted architecture/model\n"
    )
    assert not (repo / "architecture" / "model").exists()
    assert (repo / "architecture" / "model.c4").read_text(encoding="utf-8") == SPEC + PYTHON
    current = config.current_format()
    assert (repo / CONFIG).read_text(encoding="utf-8") == f"# repo config\nformat: {current}\ntracker: linear\n"


@pytest.mark.parametrize("kind", list(REPOS))
def test_verification_mismatch_writes_nothing(tmp_path, monkeypatch, capsys, kind):
    repo = REPOS[kind](tmp_path)
    before = snapshot(repo)
    real = c4_migrate.parse_views

    def skewed(*args: Any, **kwargs: Any) -> Any:
        parsed = real(*args, **kwargs)
        root = Path(kwargs.get("root", args[0] if args else ""))
        if root.resolve() != repo.resolve():
            return parsed.model_copy(update={"findings": [*parsed.findings, "skewed"]})
        return parsed

    monkeypatch.setattr(c4_migrate, "parse_views", skewed)
    assert migrate(repo) == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", MISMATCH)
    assert snapshot(repo) == before


def test_arc42_keys_convert_in_a_canonical_repo(tmp_path, capsys):
    repo = arc42_repo(tmp_path, legacy=False)
    assert migrate(repo) == 0
    assert capsys.readouterr().out == (
        "wrote architecture/model.c4\nwrote architecture/index.yaml\nwrote living-architecture.yaml\n" + ARC42_REPORT
    )
    assert (repo / "architecture" / "model.c4").read_text(encoding="utf-8") == SPEC + ARC42_DONE
    assert (repo / "architecture" / "index.yaml").read_text(encoding="utf-8") == ARC42_INDEX.replace(
        "architecture/rules/rules.arc42.md", "architecture/rules.arc42.md"
    ).replace("architecture/core.arc42.md:", "architecture/python.core.arc42.md:")
    assert (repo / "architecture" / "python.core.arc42.md").read_text(encoding="utf-8") == "# Core\n"
    assert (repo / "architecture" / "rules.arc42.md").read_text(encoding="utf-8") == "# Rules\n"
    assert not (repo / "architecture" / "core.arc42.md").exists()
    assert (repo / "architecture" / "rules").is_dir()


def test_legacy_layout_and_arc42_keys_convert_in_one_run(tmp_path, capsys):
    repo = arc42_repo(tmp_path, legacy=True)
    assert migrate(repo) == 0
    assert capsys.readouterr().out == (
        "wrote architecture/model.c4\nwrote architecture/index.yaml\nwrote living-architecture.yaml\n"
        + ARC42_REPORT
        + "deleted architecture/model/python.c4\ndeleted architecture/model/specification.c4\ndeleted architecture/model\n"
    )
    assert (repo / "architecture" / "model.c4").read_text(encoding="utf-8") == SPEC + ARC42_DONE


def test_second_run_has_nothing_to_migrate(tmp_path, capsys):
    repo = arc42_repo(tmp_path, legacy=True)
    assert migrate(repo) == 0
    capsys.readouterr()
    before = snapshot(repo)
    assert migrate(repo) == 0
    assert capsys.readouterr().out.startswith("nothing to migrate: ")
    assert snapshot(repo) == before


@pytest.mark.parametrize(
    ("migrate_case", "check_case", "rel"),
    [("arch-migrate-multi-file", "arch-check-migrated-ok", "architecture/model.c4"),
     ("arch-migrate-parse-findings", "arch-check-migrated-parse-findings", "architecture/model.c4"),
     ("arch-migrate-legacy-and-arc42-keys", "arch-check-migrated-arc42", "architecture/model.c4"),
     ("arch-migrate-stamp-after-comments", "config-show-migrated", CONFIG)],
)
def test_migrated_check_cases_check_the_migrate_golden(migrate_case, check_case, rel):
    """The migrated-check cases check exactly what their migrate case writes."""
    written = CASES / migrate_case / "files" / rel
    checked = CASES / check_case / "repo" / rel
    assert written.read_bytes() == checked.read_bytes()


# ---- the chain of steps keyed by source format, with a fake registry and format list

F1, F2, F3 = "1.0.0", "2.0.0", "3.0.0"
Apply: TypeAlias = "Callable[[Path, c4_migrate.Transaction], None]"


def _noop(_root: Path, _tx: c4_migrate.Transaction) -> None:
    pass


def chain(*applies: Apply, formats: list[str], log: list[str | None] | None = None) -> list[c4_migrate.MigrationStep]:
    """One step per apply: the unversioned step to formats[0], then each released format to the next."""
    sources: list[str | None] = [None, *formats[:-1]]

    def logged(source: str | None, apply: Apply) -> Apply:
        def run(root: Path, tx: c4_migrate.Transaction) -> None:
            if log is not None:
                log.append(source)
            apply(root, tx)

        return run

    return [
        c4_migrate.MigrationStep(source=source, target=target, apply=logged(source, apply))
        for source, target, apply in zip(sources, formats, applies, strict=True)
    ]


def chain_repo(tmp_path: Path, config_text: str, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / CONFIG).write_text(config_text, encoding="utf-8")
    for rel, text in (files or {}).items():
        (root / rel).write_text(text, encoding="utf-8")
    return root


def run_chain(root: Path, steps: list[c4_migrate.MigrationStep], formats: list[str]) -> list[str]:
    return c4_migrate.migrate(root, steps=steps, formats=formats)


def wrote(rel: str) -> str:
    return f"wrote {rel}"


def test_every_released_older_format_has_a_step_to_the_next() -> None:
    formats = config.released_formats()
    steps = c4_migrate.STEPS
    unversioned = [s for s in steps if s.source is None]
    assert [s.target for s in unversioned] == [formats[0]]
    versioned = [(s.source, s.target) for s in steps if s.source is not None]
    assert len({source for source, _ in versioned}) == len(versioned), versioned
    assert dict(versioned) == dict(itertools.pairwise(formats))


def test_an_unversioned_repo_runs_every_step_on_what_the_earlier_left(tmp_path):
    root = chain_repo(tmp_path, "tracker: linear\n")
    log: list[str | None] = []

    def second(root: Path, tx: c4_migrate.Transaction) -> None:
        assert (root / "a.txt").read_text(encoding="utf-8") == "a\n"
        tx.create("b.txt", "b\n")

    steps = chain(lambda _r, tx: tx.create("a.txt", "a\n"), second, formats=[F1, F2], log=log)
    assert run_chain(root, steps, [F1, F2]) == [wrote("a.txt"), wrote("b.txt"), wrote(CONFIG)]
    assert log == [None, F1]
    assert (root / CONFIG).read_text(encoding="utf-8") == f"format: {F2}\ntracker: linear\n"


@pytest.mark.parametrize(("declared", "ran"), [(F1, [F1, F2]), (F2, [F2])])
def test_a_released_older_format_runs_only_the_steps_from_it(tmp_path, declared, ran):
    root = chain_repo(tmp_path, f"tracker: linear\nformat: {declared}  # repo format\n")
    log: list[str | None] = []
    steps = chain(_noop, _noop, _noop, formats=[F1, F2, F3], log=log)
    assert run_chain(root, steps, [F1, F2, F3]) == [wrote(CONFIG)]
    assert log == ran
    assert (root / CONFIG).read_text(encoding="utf-8") == f"tracker: linear\nformat: {F3}  # repo format\n"


@pytest.mark.parametrize("declared", ["2.0.0", "0.5.0"], ids=["between-released", "before-the-first"])
def test_an_unreleased_older_format_is_refused(tmp_path, declared):
    root = chain_repo(tmp_path, f"format: {declared}\n")
    before = snapshot(root)
    log: list[str | None] = []
    steps = chain(lambda _r, tx: tx.create("a.txt", "a\n"), lambda _r, tx: tx.create("b.txt", "b\n"),
                  formats=[F1, F3], log=log)
    with pytest.raises(c4_migrate.MigrateError) as info:
        run_chain(root, steps, [F1, F3])
    assert str(info.value) == contract.message("arch-migrate.unknown-format", declared=declared, current=F3)
    assert log == []
    assert snapshot(root) == before


def test_the_current_format_of_the_injected_list_has_nothing_to_migrate(tmp_path):
    root = chain_repo(tmp_path, f"format: {F2}\n")
    log: list[str | None] = []
    steps = chain(_noop, _noop, formats=[F1, F2], log=log)
    assert run_chain(root, steps, [F1, F2]) == [contract.message("arch-migrate.nothing", current=F2)]
    assert log == []


def test_a_format_newer_than_the_injected_list_is_refused(tmp_path):
    root = chain_repo(tmp_path, f"format: {F3}\n")
    steps = chain(_noop, _noop, formats=[F1, F2])
    with pytest.raises(c4_migrate.MigrateError) as info:
        run_chain(root, steps, [F1, F2])
    assert str(info.value) == contract.message("format.newer", declared=F3, current=F2)


@pytest.mark.parametrize("text", ["{tracker: linear}\n", f"format:\n  {F1}\n"], ids=["unversioned", "versioned"])
def test_the_stamp_is_decided_before_any_step_writes(tmp_path, text):
    root = chain_repo(tmp_path, text, {"kept.txt": "kept\n"})
    before = snapshot(root)
    steps = chain(lambda _r, tx: tx.create("a.txt", "a\n"), lambda _r, tx: tx.delete("kept.txt"), formats=[F1, F2])
    with pytest.raises(c4_migrate.MigrateError) as info:
        run_chain(root, steps, [F1, F2])
    assert str(info.value) == contract.message("arch-migrate.stamp-mismatch", current=F2)
    assert snapshot(root) == before


# ---- one transaction and one rollback across the chain

ROLLBACK_FILES = {"moved.txt": "moved\n", "doomed.txt": "doomed\n", "replaced.txt": "replaced\n"}


def rollback_repo(tmp_path: Path) -> Path:
    root = chain_repo(tmp_path, UNVERSIONED, ROLLBACK_FILES)
    # Non-default modes, so a rollback that loses them changes the snapshot.
    for rel, mode in {"moved.txt": 0o600, "doomed.txt": 0o640, "replaced.txt": 0o604, CONFIG: 0o640}.items():
        (root / rel).chmod(mode)
    (root / "gone").mkdir()
    (root / "gone").chmod(0o750)
    return root


def every_change(_root: Path, tx: c4_migrate.Transaction) -> None:
    tx.create("created.txt", "created\n")
    tx.move("moved.txt", "arrived.txt")
    tx.delete("doomed.txt")
    tx.replace("replaced.txt", "new\n")
    tx.remove_dir("gone")


def _refuse(_root: Path, _tx: c4_migrate.Transaction) -> None:
    raise c4_migrate.MigrateError("the second step refuses")


def _mismatch(_root: Path, _tx: c4_migrate.Transaction) -> None:
    raise c4_migrate.MigrateError(contract.message("arch-migrate.mismatch"))


def _fail_applying(_root: Path, tx: c4_migrate.Transaction) -> None:
    tx.create("later.txt", "later\n")
    tx.replace("arrived.txt", "rewritten\n")
    tx.move("missing.txt", "elsewhere.txt")


@pytest.mark.parametrize(
    ("second", "refusal", "text"),
    [
        (_refuse, True, "the second step refuses"),
        (_mismatch, True, MISMATCH.removeprefix("la-arch-migrate: ").rstrip("\n")),
        (_fail_applying, False, "missing.txt"),
    ],
    ids=["planning", "verification", "application"],
)
def test_a_later_step_failure_rolls_back_the_earlier_steps(tmp_path, second, refusal, text):
    root = rollback_repo(tmp_path)
    before = snapshot(root)
    steps = chain(every_change, second, formats=[F1, F2])
    with pytest.raises(c4_migrate.MigrateError if refusal else OSError) as info:
        run_chain(root, steps, [F1, F2])
    assert (str(info.value) == text) if refusal else (text in str(info.value))
    assert snapshot(root) == before


def _recorded_chain_ops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    probe = rollback_repo(tmp_path / "probe")
    recorder = Faults(probe)
    with monkeypatch.context() as patch:
        recorder.install(patch)
        run_chain(probe, chain(every_change, _noop, formats=[F1, F2]), [F1, F2])
    assert ("rename", "moved.txt") in recorder.ops, recorder.ops
    return recorder.ops


def test_every_failed_mutation_of_a_chain_leaves_the_repo_unchanged(tmp_path, monkeypatch):
    ops = _recorded_chain_ops(tmp_path, monkeypatch)
    assert ops[-1][0] in ("rename", "replace"), ops
    for fail_at, (op, path) in enumerate(ops):
        for after in (False, True) if op == "open" else (False,):
            root = rollback_repo(tmp_path / f"run-{fail_at}-{after}")
            before = snapshot(root)
            with monkeypatch.context() as patch:
                Faults(root, fail_at=fail_at, after=after).install(patch)
                steps = chain(every_change, _noop, formats=[F1, F2])
                with pytest.raises((c4_migrate.MigrateError, OSError)):
                    run_chain(root, steps, [F1, F2])
            assert snapshot(root) == before, (fail_at, op, path, after)


def test_a_failed_restore_of_a_chain_names_every_path_left_changed(tmp_path, monkeypatch):
    ops = _recorded_chain_ops(tmp_path, monkeypatch)
    named_any = False
    for fail_at in range(len(ops)):
        root = rollback_repo(tmp_path / f"run-{fail_at}")
        before = snapshot(root)
        with monkeypatch.context() as patch:
            Faults(root, fail_at=fail_at, fail_from=True).install(patch)
            steps = chain(every_change, _noop, formats=[F1, F2])
            with pytest.raises((c4_migrate.MigrateError, OSError)) as info:
                run_chain(root, steps, [F1, F2])
        left = changed_paths(before, snapshot(root))
        text = str(info.value)
        assert [rel for rel in sorted(left) if rel not in text] == [], (fail_at, text)
        assert ("left changed" in text) is bool(left), (fail_at, text)
        named_any = named_any or bool(left)
    assert named_any, "no failure point left a path changed"


# ---- the net-effect report

NET_EFFECT: dict[str, tuple[dict[str, str], Apply, Apply, list[str]]] = {
    "one move": ({"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), _noop, [wrote(CONFIG), "moved a to b"]),
    "consecutive moves composed": (
        {"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), lambda _r, tx: tx.move("b", "c"), [wrote(CONFIG), "moved a to c"],
    ),
    "moved back": ({"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), lambda _r, tx: tx.move("b", "a"), [wrote(CONFIG)]),
    "moved then deleted": (
        {"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), lambda _r, tx: tx.delete("b"), [wrote(CONFIG), "deleted a"],
    ),
    "created then deleted": ({}, lambda _r, tx: tx.create("x", "X\n"), lambda _r, tx: tx.delete("x"), [wrote(CONFIG)]),
    "rewritten then deleted": (
        {"x": "X\n"}, lambda _r, tx: tx.replace("x", "Y\n"), lambda _r, tx: tx.delete("x"), [wrote(CONFIG), "deleted x"],
    ),
    "rewritten twice": (
        {"x": "X\n"}, lambda _r, tx: tx.replace("x", "Y\n"), lambda _r, tx: tx.replace("x", "Z\n"),
        [wrote("x"), wrote(CONFIG)],
    ),
    "moved then rewritten": (
        {"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), lambda _r, tx: tx.replace("b", "B\n"),
        [wrote("b"), wrote(CONFIG), "moved a to b"],
    ),
    "moved source recreated": (
        {"a": "A\n"}, lambda _r, tx: tx.move("a", "b"), lambda _r, tx: tx.create("a", "new\n"),
        [wrote("a"), wrote(CONFIG), "moved a to b"],
    ),
}


def _first_of_each_kind(_root: Path, tx: c4_migrate.Transaction) -> None:
    tx.delete("d")
    tx.move("m", "n")
    tx.create("w1", "1\n")


def _second_of_each_kind(_root: Path, tx: c4_migrate.Transaction) -> None:
    tx.remove_dir("e")
    tx.create("w2", "2\n")


@pytest.mark.parametrize("name", list(NET_EFFECT))
def test_the_report_is_the_net_effect(tmp_path, name):
    files, first, second, report = NET_EFFECT[name]
    root = chain_repo(tmp_path, UNVERSIONED, files)
    log: list[str | None] = []
    assert run_chain(root, chain(first, second, formats=[F1, F2], log=log), [F1, F2]) == report
    assert log == [None, F1]
    assert not [rel for rel in snapshot(root)[1] if rel.endswith(".tmp")]


def test_the_report_lists_writes_then_moves_then_deletes(tmp_path):
    root = chain_repo(tmp_path, UNVERSIONED, {"d": "D\n", "m": "M\n"})
    (root / "e").mkdir()
    report = run_chain(root, chain(_first_of_each_kind, _second_of_each_kind, formats=[F1, F2]), [F1, F2])
    assert report == [wrote("w1"), wrote("w2"), wrote(CONFIG), "moved m to n", "deleted d", "deleted e"]
