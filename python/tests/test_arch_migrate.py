"""la-arch-migrate: all-or-nothing writes under injected filesystem failures, and the verification guard."""

import builtins
import io
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from living_architecture import cli, config
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
    (tmp_path / "repo" / "architecture" / "index.yaml").write_text("python:\n  root_package: pkg\n", encoding="utf-8")
    (tmp_path / "repo" / CONFIG).write_text(UNVERSIONED, encoding="utf-8")
    if views:
        (tmp_path / "repo" / "architecture" / "views.c4").write_text(VIEWS, encoding="utf-8")
    return tmp_path / "repo"


def snapshot(root: Path) -> tuple[set[str], dict[str, bytes]]:
    """Every directory and every file's bytes under `root`."""
    dirs: set[str] = set()
    files: dict[str, bytes] = {}
    for here, subdirs, names in os.walk(root):
        dirs.update(os.path.relpath(Path(here) / d, root) for d in subdirs)
        files.update({os.path.relpath(Path(here) / n, root): (Path(here) / n).read_bytes() for n in names})
    return dirs, files


def changed_paths(before: tuple[set[str], dict[str, bytes]], after: tuple[set[str], dict[str, bytes]]) -> set[str]:
    """The directories and files that differ between two snapshots."""
    files = before[1].keys() | after[1].keys()
    return (before[0] ^ after[0]) | {rel for rel in files if before[1].get(rel) != after[1].get(rel)}


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


@pytest.mark.parametrize("views", [False, True], ids=["views-created", "views-kept"])
def test_every_failed_mutation_leaves_the_repo_unchanged(tmp_path, monkeypatch, capsys, views):
    probe = legacy_repo(tmp_path / "probe", views=views)
    recorder = Faults(probe)
    with monkeypatch.context() as patch:
        recorder.install(patch)
        assert migrate(probe) == 0
    capsys.readouterr()
    assert recorder.ops, "the migration mutated nothing under the repo"
    if views:
        assert ("open", "architecture/views.c4") not in recorder.ops
    for fail_at, (op, path) in enumerate(recorder.ops):
        for after in (False, True) if op == "open" else (False,):
            repo = legacy_repo(tmp_path / f"run-{fail_at}-{after}", views=views)
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


def test_verification_mismatch_writes_nothing(tmp_path, monkeypatch, capsys):
    repo = legacy_repo(tmp_path, views=True)
    before = snapshot(repo)
    real = c4_migrate.parse_views

    def skewed(*args: Any, **kwargs: Any) -> Any:
        parsed = real(*args, **kwargs)
        root = Path(kwargs.get("root", args[0] if args else ""))
        if (root / "architecture" / "model.c4").is_file():
            return parsed.model_copy(update={"findings": [*parsed.findings, "skewed"]})
        return parsed

    monkeypatch.setattr(c4_migrate, "parse_views", skewed)
    assert migrate(repo) == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", MISMATCH)
    assert snapshot(repo) == before


@pytest.mark.parametrize(
    ("migrate_case", "check_case", "rel"),
    [("arch-migrate-multi-file", "arch-check-migrated-ok", "architecture/model.c4"),
     ("arch-migrate-parse-findings", "arch-check-migrated-parse-findings", "architecture/model.c4"),
     ("arch-migrate-stamp-after-comments", "config-show-migrated", CONFIG)],
)
def test_migrated_check_cases_check_the_migrate_golden(migrate_case, check_case, rel):
    """The migrated-check cases check exactly what their migrate case writes."""
    written = CASES / migrate_case / "files" / rel
    checked = CASES / check_case / "repo" / rel
    assert written.read_bytes() == checked.read_bytes()
