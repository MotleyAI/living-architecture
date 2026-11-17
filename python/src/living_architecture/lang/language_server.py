"""The bundled basedpyright language server: one isolated, patched stdio session answering position queries and
exporting occurrence indexes."""

from __future__ import annotations

import bisect
import contextlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Literal, Self, cast
from urllib.parse import urlparse
from urllib.request import url2pathname

import basedpyright
from nodejs_wheel import executable as node_wheel
from pydantic import BaseModel, ConfigDict

from living_architecture.contract import language, os_error_text
from living_architecture.lang.typecheck import (
    pyright_export_env,
    pyright_patch_env,
    read_pyright_export,
    read_pyright_patch,
)

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ISOLATION = {"PYTHONSAFEPATH": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
_EOF = object()
EXPORT_COMMAND = "la.exportOccurrences"
OccurrenceKind = Literal["name", "member", "keyword", "import", "alias", "module", "forward-reference", "all-entry"]
FactKind = Literal["definition", "typeDefinition", "verdict", "access", "class"]
Verdict = Literal["Unknown", "Any"]


class LanguageServerError(Exception):
    """The language server could not start (`start`), exited (`exit`, with its exit `code`), answered an error
    (`error`) or is not patched; `stderr` is what it wrote, known once its session is stopped."""

    def __init__(self, error: str, *, kind: Literal["start", "exit", "error", "other"] = "other") -> None:
        super().__init__(error)
        self.error = error
        self.kind = kind
        self.code: int | None = None
        self.stderr = ""


class Span(BaseModel):
    """Characters `[start, end)` of the file at `path`."""

    model_config = ConfigDict(frozen=True)

    path: Path
    start: int
    end: int


class Diagnostic(BaseModel):
    """A checker diagnostic: its span, rule, LSP severity (1 error, 2 warning, 3 information, 4 hint) and message."""

    model_config = ConfigDict(frozen=True)

    span: Span
    code: str
    severity: int
    message: str


class Declaration(BaseModel):
    """A declaration an occurrence resolves to, as the definition request finds it: its name's span."""

    model_config = ConfigDict(frozen=True)

    span: Span


class Occurrence(BaseModel):
    """An occurrence of an exported name: its span, kind, declarations, the import bindings it passes through on the
    way to them (each the span of the name it binds, in order) and, for a member access, whether the checker types its
    receiver `Unknown` or `Any`."""

    model_config = ConfigDict(frozen=True)

    span: Span
    name: str
    kind: OccurrenceKind
    declarations: tuple[Declaration, ...] = ()
    bindings: tuple[Span, ...] = ()
    receiver: Verdict | None = None


class FactQuery(BaseModel):
    """What to export about the position `offset` of `path`."""

    model_config = ConfigDict(frozen=True)

    path: Path
    offset: int
    kinds: tuple[FactKind, ...]


class PositionFacts(BaseModel):
    """The facts exported about one position: definitions and type definitions as those requests find them, the
    hover verdict there, for a member name the verdict of its access's receiver, and for a class name its ancestors in MRO order (each
    class by its name) and the request's member names a class of it outside the project declares."""

    model_config = ConfigDict(frozen=True)

    path: Path
    offset: int
    kinds: tuple[FactKind, ...]
    definition: tuple[Span, ...] = ()
    type_definition: tuple[Span, ...] = ()
    verdict: Verdict | None = None
    access: Verdict | None = None
    ancestors: tuple[Span, ...] = ()
    members: tuple[str, ...] = ()


class ExportRequest(BaseModel):
    """The names whose occurrences to export from `files` (opened), the position facts to export, and the member names
    the class facts look up."""

    model_config = ConfigDict(frozen=True)

    names: list[str]
    files: list[Path]
    facts: list[FactQuery] = []
    members: list[str] = []


class OccurrenceIndex(BaseModel):
    """An export: the occurrences, the facts asked for, in request order, and the facts the export followed."""

    occurrences: list[Occurrence] = []
    answers: list[PositionFacts] = []
    followed: list[PositionFacts] = []


def _line_starts(text: str) -> list[int]:
    return [0, *(m.end() for m in _LINE_BREAK.finditer(text))]


def _units(char: str) -> int:
    return 2 if ord(char) > 0xFFFF else 1


def utf16_index(text: str, line: int, character: int, starts: list[int] | None = None) -> int:
    """The character index of an LSP position (0-based line, UTF-16 column); `starts` is `text`'s line starts, when
    known."""
    starts = _line_starts(text) if starts is None else starts
    index = starts[min(line, len(starts) - 1)]
    units = 0
    while units < character and index < len(text) and text[index] not in "\r\n":
        units += _units(text[index])
        index += 1
    return index


def utf16_position(text: str, index: int, starts: list[int] | None = None) -> tuple[int, int]:
    """The LSP position (0-based line, UTF-16 column) of a character index; `starts` is `text`'s line starts, when
    known."""
    starts = _line_starts(text) if starts is None else starts
    line = bisect.bisect_right(starts, index) - 1
    return line, sum(_units(c) for c in text[starts[line] : index])


def _bundled_command() -> list[str]:
    bin_dir = node_wheel.ROOT_DIR if os.name == "nt" else os.path.join(node_wheel.ROOT_DIR, "bin")
    entry = Path(next(iter(basedpyright.__path__))) / "langserver.index.js"
    return [os.path.join(bin_dir, "node"), str(entry), "--stdio"]


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as fh:
        return fh.read()


def _path_of(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


def _close_streams(proc: subprocess.Popen[bytes]) -> None:
    for stream in (proc.stdin, proc.stdout):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()


def _as_list(result: Any) -> list[Any]:
    if isinstance(result, list):
        return cast(list[Any], result)
    return [result] if result else []


class LanguageServer:
    """A basedpyright session over `workspace`, started from la's environment with the pyright#11919 patch.

    It runs outside the workspace with the interpreter isolated, so it writes nothing there and runs no project code.
    `read` supplies a file's text for position conversion (default: the file on disk, read once).
    """

    def __init__(
        self, workspace: Path, *, command: list[str] | None = None, read: Callable[[Path], str] | None = None
    ) -> None:
        self.workspace = workspace
        self._command = command or _bundled_command()
        self._read = read or _read_text
        self._texts: dict[Path, str] = {}
        self._starts: dict[Path, list[int]] = {}
        self._versions: dict[Path, int] = {}
        self._next_id = 0
        self._messages: queue.Queue[Any] = queue.Queue()
        self._proc: subprocess.Popen[bytes] | None = None
        self._scratch: str | None = None
        self._stderr: list[bytes] = []
        self._stderr_reader: threading.Thread | None = None
        self._failure: LanguageServerError | None = None

    def __enter__(self) -> Self:
        try:
            self._start()
        except BaseException:
            self._stop()
            raise
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._stop()

    def _start(self) -> None:
        self._scratch = tempfile.mkdtemp(prefix="la-langserver-")
        result = Path(self._scratch) / "patch.json"
        exported = Path(self._scratch) / "export.json"
        python = language("python")
        inherited = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        patched = pyright_patch_env(inherited, result=result, versions=python["checker_patch_versions"])
        env = {**pyright_export_env(patched, result=exported, versions=python["checker_export_versions"]), **_ISOLATION}
        try:
            self._proc = subprocess.Popen(
                self._command,
                bufsize=0,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._scratch,
                env=env,
            )
        except OSError as exc:
            raise self._fail(os_error_text(exc, self.workspace), "start") from None
        assert self._proc.stdout is not None and self._proc.stderr is not None
        threading.Thread(target=self._pump, args=(self._proc.stdout,), daemon=True).start()
        self._stderr_reader = threading.Thread(target=self._drain, args=(self._proc.stderr,), daemon=True)
        self._stderr_reader.start()
        uri = self.workspace.as_uri()
        self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": uri,
            "workspaceFolders": [{"uri": uri, "name": self.workspace.name}],
            "capabilities": {
                "workspace": {"configuration": True, "workspaceFolders": True},
                "textDocument": {"hover": {"contentFormat": ["plaintext"]}},
            },
        })
        patch = read_pyright_patch(result)
        export = read_pyright_export(exported)
        if patch is None or patch.outcome != "patched" or export is None or export.outcome != "patched":
            raise self._fail("unpatched", "other")
        self._notify("initialized", {})
        self._await_configuration()
        found = self._execute({"names": [], "files": []})
        if not isinstance(found, dict) or not isinstance(cast(dict[str, Any], found).get("occurrences"), list):
            raise self._fail("export", "other")

    def _fail(self, error: str, kind: Literal["start", "exit", "error", "other"]) -> LanguageServerError:
        """The error to raise, its stderr and exit code filled in when the session stops."""
        if self._failure is None:
            self._failure = LanguageServerError(error, kind=kind)
        return self._failure

    def _stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            if self._failure is not None and self._failure.kind == "exit":
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=10)
            self._terminate(proc)
            _close_streams(proc)
            if self._stderr_reader is not None:
                self._stderr_reader.join(timeout=10)
            if proc.stderr is not None:
                with contextlib.suppress(OSError):
                    proc.stderr.close()
            if self._failure is not None:
                self._failure.stderr = b"".join(self._stderr).decode(errors="replace")
                self._failure.code = proc.returncode if self._failure.kind == "exit" else None
        if self._scratch is not None:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None

    def _terminate(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is not None:
            return
        try:
            self._send({"jsonrpc": "2.0", "id": self._new_id(), "method": "shutdown", "params": None}, proc)
            self._send({"jsonrpc": "2.0", "method": "exit", "params": None}, proc)
            proc.wait(timeout=10)
        except (LanguageServerError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()

    def _pump(self, stream: IO[bytes]) -> None:
        try:
            while True:
                length = 0
                while (line := stream.readline()) not in (b"\r\n", b"\n", b""):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                if not line or not length:
                    break
                chunks: list[bytes] = []
                left = length
                while left and (chunk := stream.read(left)):
                    chunks.append(chunk)
                    left -= len(chunk)
                self._messages.put(json.loads(b"".join(chunks)))
        except (OSError, ValueError):
            pass
        self._messages.put(_EOF)

    def _drain(self, stream: IO[bytes]) -> None:
        with contextlib.suppress(OSError, ValueError):
            while chunk := stream.read(65536):
                self._stderr.append(chunk)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _send(self, payload: dict[str, Any], proc: subprocess.Popen[bytes] | None = None) -> None:
        proc = proc or self._proc
        if proc is None or proc.stdin is None:
            raise self._fail("not running", "other")
        body = json.dumps(payload).encode()
        frame = memoryview(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        try:
            while frame:
                frame = frame[proc.stdin.write(frame) :]
            proc.stdin.flush()
        except OSError:
            raise self._fail("exited", "exit") from None

    def _notify(self, method: str, params: object) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: object) -> Any:
        request_id = self._new_id()
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            msg = self._next()
            if "method" in msg and "id" in msg:
                self._answer(msg)
            elif msg.get("id") == request_id and "method" not in msg:
                if "error" in msg:
                    raise self._fail(str(msg["error"].get("message", "")), "error")
                return msg.get("result")

    def _await_configuration(self) -> None:
        """Wait for the server to ask for its settings, so it analyses with the project's own configuration."""
        while True:
            msg = self._next()
            if "method" in msg and "id" in msg:
                self._answer(msg)
                if msg["method"] == "workspace/configuration":
                    return

    def _next(self) -> dict[str, Any]:
        msg = self._messages.get()
        if msg is _EOF:
            self._messages.put(_EOF)
            raise self._fail("exited", "exit")
        return msg

    def _answer(self, msg: dict[str, Any]) -> None:
        result = None
        if msg["method"] == "workspace/configuration":
            result = [None] * len(msg.get("params", {}).get("items", []))
        self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    def _text(self, path: Path) -> str:
        if path not in self._texts:
            self._texts[path] = self._read(path)
        return self._texts[path]

    def _index(self, path: Path, position: dict[str, Any]) -> int:
        """The character index in `path`'s text of an LSP position, its line starts computed once per text."""
        text = self._text(path)
        if path not in self._starts:
            self._starts[path] = _line_starts(text)
        return utf16_index(text, position["line"], position["character"], self._starts[path])

    def open(self, path: Path, text: str) -> None:
        """Hand the server `text` as the content of `path`; a path already open is changed to it."""
        if path in self._versions:
            if self._texts.get(path) != text:
                self.change(path, text)
            return
        self._texts[path] = text
        self._starts.pop(path, None)
        self._versions[path] = 1
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": path.as_uri(), "languageId": "python", "version": 1, "text": text}
        })

    def change(self, path: Path, text: str) -> None:
        """Replace the content of `path`, opened before, with `text`."""
        self._texts[path] = text
        self._starts.pop(path, None)
        self._versions[path] += 1
        self._notify("textDocument/didChange", {
            "textDocument": {"uri": path.as_uri(), "version": self._versions[path]},
            "contentChanges": [{"text": text}],
        })

    def _position(self, path: Path, offset: int) -> dict[str, Any]:
        text = self._text(path)
        if path not in self._starts:
            self._starts[path] = _line_starts(text)
        line, character = utf16_position(text, offset, self._starts[path])
        return {"textDocument": {"uri": path.as_uri()}, "position": {"line": line, "character": character}}

    def _span(self, location: dict[str, Any]) -> Span | None:
        uri = location.get("targetUri", location.get("uri"))
        rng = location.get("targetSelectionRange", location.get("range"))
        if uri is None or rng is None:
            return None
        path = _path_of(uri)
        try:
            return Span(path=path, start=self._index(path, rng["start"]), end=self._index(path, rng["end"]))
        except OSError:
            return None

    def _locations(self, method: str, path: Path, offset: int, extra: dict[str, Any] | None = None) -> list[Span]:
        result = self._request(method, {**self._position(path, offset), **(extra or {})})
        return list(self._spans(_as_list(result)))

    def definition(self, path: Path, offset: int) -> list[Span]:
        return self._locations("textDocument/definition", path, offset)

    def diagnostics(self, path: Path) -> list[Diagnostic]:
        """The diagnostics of `path` as its current text stands (a pull request)."""
        result = self._request("textDocument/diagnostic", {"textDocument": {"uri": path.as_uri()}})
        text = self._text(path)
        starts = _line_starts(text)
        out: list[Diagnostic] = []
        for item in (result or {}).get("items", []):
            start, end = item["range"]["start"], item["range"]["end"]
            span = Span(path=path, start=utf16_index(text, start["line"], start["character"], starts),
                        end=utf16_index(text, end["line"], end["character"], starts))
            out.append(Diagnostic(span=span, code=str(item.get("code", "")), severity=int(item.get("severity", 1)),
                                  message=str(item.get("message", ""))))
        return out

    def _execute(self, request: dict[str, Any]) -> Any:
        return self._request("workspace/executeCommand", {"command": EXPORT_COMMAND, "arguments": [request]})

    def _exported_span(self, item: dict[str, Any], name: str) -> Span:
        """An occurrence's range in the text its file was opened with; `LanguageServerError` unless it spells `name`."""
        path = _path_of(item["uri"])
        span = Span(path=path, start=self._index(path, item["range"]["start"]), end=self._index(path, item["range"]["end"]))
        if self._text(path)[span.start : span.end] != name:
            raise self._fail("export", "other")
        return span

    def _declaration(self, location: dict[str, Any]) -> Declaration | None:
        """A declaration's span from its name on: a `*args` or `**kwargs` parameter's stars left out."""
        span = self._span(location)
        if span is None:
            return None
        text = self._text(span.path)
        start = span.start
        while start < span.end and text[start] in "* \t":
            start += 1
        return Declaration(span=span.model_copy(update={"start": start}))

    def _spans(self, locations: list[dict[str, Any]] | None) -> tuple[Span, ...]:
        spans = (self._span(d) for d in locations or [])
        return tuple(s for s in spans if s is not None)

    def _declarations(self, locations: list[dict[str, Any]] | None) -> tuple[Declaration, ...]:
        found = (self._declaration(d) for d in locations or [])
        return tuple(d for d in found if d is not None)

    def _facts(self, item: dict[str, Any], path: Path | None = None, offset: int | None = None) -> PositionFacts:
        if path is None or offset is None:
            path = _path_of(item["uri"])
            position = item["position"]
            offset = self._index(path, position)
        kinds = tuple(k for k in ("definition", "typeDefinition", "verdict", "access", "class") if k in item)
        found = cast(dict[str, Any], item.get("class") or {})
        return PositionFacts(
            path=path, offset=offset, kinds=cast(tuple[FactKind, ...], kinds),
            definition=self._spans(item.get("definition")),
            type_definition=self._spans(item.get("typeDefinition")),
            verdict=item.get("verdict"), access=item.get("access"),
            ancestors=self._spans(found.get("mro")), members=tuple(str(m) for m in found.get("members") or []),
        )

    def _followed(self, items: list[dict[str, Any]] | None) -> list[PositionFacts]:
        """The followed facts, each in a file that can be read."""
        out: list[PositionFacts] = []
        for item in items or []:
            with contextlib.suppress(OSError):
                out.append(self._facts(item))
        return out

    def export(self, request: ExportRequest) -> OccurrenceIndex:
        """The occurrences of `request.names` in its files (opened before) and its position facts, in one request."""
        result = self._execute({
            "names": request.names,
            "files": [p.as_uri() for p in request.files],
            "facts": [{"uri": q.path.as_uri(), "position": self._position(q.path, q.offset)["position"], "kinds": list(q.kinds)}
                      for q in request.facts],
            "members": request.members,
        })
        if not isinstance(result, dict):
            raise self._fail("export", "error")
        found = cast(dict[str, Any], result)
        occurrences = [
            Occurrence(
                span=self._exported_span(item, item["name"]), name=item["name"], kind=item["kind"],
                declarations=self._declarations(item.get("declarations")),
                bindings=self._spans(item.get("bindings")),
                receiver=item.get("receiver"),
            )
            for item in found.get("occurrences") or []
        ]
        answers = [self._facts(item, q.path, q.offset) for q, item in zip(request.facts, found.get("answers") or [], strict=True)]
        followed = self._followed(found.get("followed"))
        return OccurrenceIndex(occurrences=occurrences, answers=answers, followed=followed)
