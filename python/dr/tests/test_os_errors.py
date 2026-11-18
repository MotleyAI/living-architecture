"""OS errors render from the shared os.* templates; only a missing path counts as absent."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest
import yaml

from deterministic_refactor.contract import is_regular_file, os_error_reason, os_error_text

SHARED = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir()) / "shared"
VECTORS = yaml.safe_load((SHARED / "vectors" / "os-errors.yaml").read_text(encoding="utf-8"))
UNPRIVILEGED = hasattr(os, "geteuid") and os.geteuid() != 0


def _error(code: str | None, path: object = None, dest: object = None) -> OSError:
    """An OSError as the runtime raises it, with runtime wording the renderer must not print."""
    number = None if code is None else getattr(errno, code)
    if path is None and dest is None:
        return OSError(number, "runtime wording") if number is not None else OSError("runtime wording")
    return OSError(number, "runtime wording", path, None, dest)


@pytest.mark.parametrize(("code", "reason"), VECTORS["reasons"], ids=lambda v: str(v))
def test_reason(code: str | None, reason: str) -> None:
    assert os_error_reason(_error(code, "/r/a")) == reason


@pytest.mark.parametrize("vector", VECTORS["cases"], ids=lambda v: v["name"])
def test_text(vector: dict) -> None:
    error = _error(vector["code"], vector["error_path"], vector.get("error_dest"))
    expected = vector["text"].replace("<CWD>", os.getcwd())
    assert os_error_text(error, vector["root"], vector["path"]) == expected


def test_text_takes_path_objects(tmp_path: Path) -> None:
    error = _error("EACCES", str(tmp_path / "a" / "b.yaml"))
    assert os_error_text(error, tmp_path, tmp_path / "a" / "c.yaml") == "a/c.yaml: permission denied"


def test_regular_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    assert is_regular_file(tmp_path / "f") is True


def test_missing_is_absent(tmp_path: Path) -> None:
    assert is_regular_file(tmp_path / "missing") is False
    assert is_regular_file(tmp_path / "missing" / "f") is False


def test_non_regular_is_absent(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    assert is_regular_file(tmp_path / "d") is False


def test_symlink_to_regular_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    (tmp_path / "link").symlink_to("f")
    assert is_regular_file(tmp_path / "link") is True


def test_under_a_regular_file_raises(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x", encoding="utf-8")
    with pytest.raises(OSError) as info:
        is_regular_file(tmp_path / "f" / "index.yaml")
    assert info.value.errno == errno.ENOTDIR


def test_symlink_loop_raises(tmp_path: Path) -> None:
    (tmp_path / "loop").symlink_to("loop")
    with pytest.raises(OSError) as info:
        is_regular_file(tmp_path / "loop")
    assert info.value.errno == errno.ELOOP


@pytest.mark.skipif(not UNPRIVILEGED, reason="needs a non-root POSIX user")
def test_untraversable_directory_raises(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "f").write_text("x", encoding="utf-8")
    locked.chmod(0)
    try:
        with pytest.raises(OSError) as info:
            is_regular_file(locked / "f")
        assert info.value.errno == errno.EACCES
    finally:
        locked.chmod(0o755)
