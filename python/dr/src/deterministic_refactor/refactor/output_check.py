"""The validity check every Python refactor's write passes: the new bytes decode to the new text, and a file that
parsed still parses."""

from __future__ import annotations

from pathlib import Path

from deterministic_refactor.contract import language_of, message
from deterministic_refactor.refactor.locators import RefactorError
from deterministic_refactor.refactor.python_project import Snapshot, read_str_coding
from deterministic_refactor.refactor.python_source import SourceFile
from deterministic_refactor.refactor.writer import FileWrite

_BOM = b"\xef\xbb\xbf"


def _unencodable(rel: str, encoding: str) -> RefactorError:
    return RefactorError(message("refactor.unencodable", path=rel, encoding=encoding))


def _parses(rel: str, text: str) -> None:
    """`refactor.unparsable` when Python file `rel` does not parse as `text`."""
    if SourceFile(Path(rel), text).tree is None:
        raise RefactorError(message("refactor.unparsable", path=rel))


def _reads_back(rel: str, data: bytes, text: str) -> None:
    """`refactor.unencodable` unless `data`, decoded as a fresh read would, is `text`."""
    body = data.removeprefix(_BOM)
    declared = read_str_coding(body) or "utf-8"
    try:
        same = body.decode(declared) == text
    except (UnicodeDecodeError, LookupError):
        same = False
    if not same:
        raise _unencodable(rel, declared)


def checked_write(snapshot: Snapshot, rel: str, text: str) -> FileWrite:
    """The write of `text` to `rel`, a file of `snapshot`, named in a refusal as it was read."""
    try:
        data = snapshot.encode(rel, text)
    except UnicodeEncodeError as exc:
        raise _unencodable(rel, snapshot.encoding(rel)) from exc
    _reads_back(rel, data, text)
    if language_of(rel) == "python" and snapshot.source(rel).tree is not None:
        _parses(rel, text)
    return FileWrite(rel=rel, old=snapshot.data(rel), new=data)


def checked_create(rel: str, text: str) -> FileWrite:
    """The write of `text` to the new file `rel`, as UTF-8."""
    if language_of(rel) == "python":
        _parses(rel, text)
    return FileWrite(rel=rel, old=None, new=text.encode())
