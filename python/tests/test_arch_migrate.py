"""la-arch-migrate: all-or-nothing writes under injected filesystem failures, and the verification guard."""

import builtins
import io
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from living_architecture import cli
from living_architecture.c4 import migrate as c4_migrate

CASES = next(p for p in Path(__file__).resolve().parents if (p / "conformance").is_dir()) / "conformance" / "cases"

SPEC = "specification {\n  element system\n  element node\n}\n"
PYTHON = "model {\n  python = system 'Python' {\n    core = node 'Core'\n    db = node 'DB'\n    core -> db\n  }\n}\n"
VIEWS = "views {\n  view land of python {\n    include *\n  }\n}\n"
MISMATCH = "la-arch-migrate: the merged files would not parse to the same model and views; nothing written\n"
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def legacy_repo(tmp_path: Path, *, views: bool) -> Path:
    model = tmp_path / "repo" / "architecture" / "model"
    model.mkdir(parents=True)
    (model / "specification.c4").write_text(SPEC, encoding="utf-8")
    (model / "python.c4").write_text(PYTHON, encoding="utf-8")
    (tmp_path / "repo" / "architecture" / "index.yaml").write_text("python:\n  root_package: pkg\n", encoding="utf-8")
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
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


REPOS: dict[str, Callable[[Path], Path]] = {
    "views-created": lambda tmp: legacy_repo(tmp, views=False),
    "views-kept": lambda tmp: legacy_repo(tmp, views=True),
    "arc42-canonical": lambda tmp: arc42_repo(tmp, legacy=False),
    "arc42-legacy": lambda tmp: arc42_repo(tmp, legacy=True),
}


def snapshot(root: Path) -> tuple[set[str], dict[str, bytes]]:
    """Every directory and every file's bytes under `root`."""
    dirs: set[str] = set()
    files: dict[str, bytes] = {}
    for here, subdirs, names in os.walk(root):
        dirs.update(os.path.relpath(Path(here) / d, root) for d in subdirs)
        files.update({os.path.relpath(Path(here) / n, root): (Path(here) / n).read_bytes() for n in names})
    return dirs, files


class Faults:
    """Records every filesystem mutation under `root` and fails the `fail_at`-th one.

    `after` makes a failing create happen first (the file exists, then the write fails).
    """

    def __init__(self, root: Path, fail_at: int | None = None, after: bool = False) -> None:
        self.root = str(root.resolve())
        self.fail_at = fail_at
        self.after = after
        self.ops: list[tuple[str, str]] = []

    def _mine(self, path: Any) -> str | None:
        if isinstance(path, int):
            return None
        full = os.path.abspath(os.fspath(path))
        return full if full == self.root or full.startswith(self.root + os.sep) else None

    def _hit(self, op: str, path: str) -> bool:
        self.ops.append((op, os.path.relpath(path, self.root)))
        return self.fail_at is not None and len(self.ops) - 1 == self.fail_at

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


def test_successful_migration_removes_the_emptied_model_directory(tmp_path, capsys):
    repo = legacy_repo(tmp_path, views=True)
    assert migrate(repo) == 0
    assert capsys.readouterr().out == (
        "wrote architecture/model.c4\n"
        "deleted architecture/model/python.c4\n"
        "deleted architecture/model/specification.c4\n"
        "deleted architecture/model\n"
    )
    assert not (repo / "architecture" / "model").exists()
    assert (repo / "architecture" / "model.c4").read_text(encoding="utf-8") == SPEC + PYTHON


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
    assert capsys.readouterr().out == "wrote architecture/model.c4\nwrote architecture/index.yaml\n" + ARC42_REPORT
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
        "wrote architecture/model.c4\nwrote architecture/index.yaml\n"
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
    ("migrate_case", "check_case"),
    [("arch-migrate-multi-file", "arch-check-migrated-ok"),
     ("arch-migrate-parse-findings", "arch-check-migrated-parse-findings"),
     ("arch-migrate-legacy-and-arc42-keys", "arch-check-migrated-arc42")],
)
def test_migrated_check_cases_check_the_migrate_golden(migrate_case, check_case):
    """The migrated-check cases check exactly what their migrate case writes."""
    written = CASES / migrate_case / "files" / "architecture" / "model.c4"
    checked = CASES / check_case / "repo" / "architecture" / "model.c4"
    assert written.read_bytes() == checked.read_bytes()
