"""The bundled basedpyright language server: one isolated, patched stdio session answering position queries."""

from __future__ import annotations

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
from typing import IO, Any, Self, cast
from urllib.parse import urlparse
from urllib.request import url2pathname

import basedpyright
from nodejs_wheel import executable as node_wheel
from pydantic import BaseModel, ConfigDict

from living_architecture.contract import language
from living_architecture.lang.typecheck import pyright_patch_env, read_pyright_patch

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ISOLATION = {"PYTHONSAFEPATH": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
_EOF = object()


class LanguageServerError(Exception):
    """The language server could not start, is not patched, failed or exited."""


class Span(BaseModel):
    """Characters `[start, end)` of the file at `path`."""

    model_config = ConfigDict(frozen=True)

    path: Path
    start: int
    end: int


def _line_starts(text: str) -> list[int]:
    return [0, *(m.end() for m in _LINE_BREAK.finditer(text))]


def _units(char: str) -> int:
    return 2 if ord(char) > 0xFFFF else 1


def utf16_index(text: str, line: int, character: int) -> int:
    """The character index of an LSP position (0-based line, UTF-16 column)."""
    starts = _line_starts(text)
    index = starts[min(line, len(starts) - 1)]
    units = 0
    while units < character and index < len(text) and text[index] not in "\r\n":
        units += _units(text[index])
        index += 1
    return index


def utf16_position(text: str, index: int) -> tuple[int, int]:
    """The LSP position (0-based line, UTF-16 column) of a character index."""
    starts = _line_starts(text)
    line = next(i for i in range(len(starts) - 1, -1, -1) if starts[i] <= index)
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
        self._versions: dict[Path, int] = {}
        self._next_id = 0
        self._messages: queue.Queue[Any] = queue.Queue()
        self._proc: subprocess.Popen[bytes] | None = None
        self._scratch: str | None = None

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
        versions: list[str] = language("python")["checker_patch_versions"]
        inherited = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env = {**pyright_patch_env(inherited, result=result, versions=versions), **_ISOLATION}
        try:
            self._proc = subprocess.Popen(
                self._command,
                bufsize=0,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self._scratch,
                env=env,
            )
        except OSError as exc:
            raise LanguageServerError(str(exc)) from None
        assert self._proc.stdout is not None
        threading.Thread(target=self._pump, args=(self._proc.stdout,), daemon=True).start()
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
        if patch is None or patch.outcome != "patched":
            raise LanguageServerError("unpatched")
        self._notify("initialized", {})
        self._await_configuration()

    def _stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            self._terminate(proc)
            _close_streams(proc)
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
                body = b""
                while len(body) < length and (chunk := stream.read(length - len(body))):
                    body += chunk
                self._messages.put(json.loads(body))
        except (OSError, ValueError):
            pass
        self._messages.put(_EOF)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _send(self, payload: dict[str, Any], proc: subprocess.Popen[bytes] | None = None) -> None:
        proc = proc or self._proc
        if proc is None or proc.stdin is None:
            raise LanguageServerError("not running")
        body = json.dumps(payload).encode()
        frame = memoryview(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        try:
            while frame:
                frame = frame[proc.stdin.write(frame) :]
            proc.stdin.flush()
        except OSError:
            raise LanguageServerError("exited") from None

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
                    raise LanguageServerError(str(msg["error"].get("message", "")))
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
            raise LanguageServerError("exited")
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

    def open(self, path: Path, text: str) -> None:
        """Hand the server `text` as the content of `path`."""
        self._texts[path] = text
        self._versions[path] = 1
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": path.as_uri(), "languageId": "python", "version": 1, "text": text}
        })

    def change(self, path: Path, text: str) -> None:
        """Replace the content of `path`, opened before, with `text`."""
        self._texts[path] = text
        self._versions[path] += 1
        self._notify("textDocument/didChange", {
            "textDocument": {"uri": path.as_uri(), "version": self._versions[path]},
            "contentChanges": [{"text": text}],
        })

    def _position(self, path: Path, offset: int) -> dict[str, Any]:
        line, character = utf16_position(self._text(path), offset)
        return {"textDocument": {"uri": path.as_uri()}, "position": {"line": line, "character": character}}

    def _span(self, location: dict[str, Any]) -> Span | None:
        uri = location.get("targetUri", location.get("uri"))
        rng = location.get("targetSelectionRange", location.get("range"))
        if uri is None or rng is None:
            return None
        path = _path_of(uri)
        try:
            text = self._text(path)
        except OSError:
            return None
        start, end = rng["start"], rng["end"]
        return Span(
            path=path,
            start=utf16_index(text, start["line"], start["character"]),
            end=utf16_index(text, end["line"], end["character"]),
        )

    def _locations(self, method: str, path: Path, offset: int, extra: dict[str, Any] | None = None) -> list[Span]:
        result = self._request(method, {**self._position(path, offset), **(extra or {})})
        return [span for item in _as_list(result) if (span := self._span(item)) is not None]

    def references(self, path: Path, offset: int) -> list[Span]:
        """Every reference to the symbol at `offset`, its declarations included."""
        return self._locations("textDocument/references", path, offset, {"context": {"includeDeclaration": True}})

    def definition(self, path: Path, offset: int) -> list[Span]:
        return self._locations("textDocument/definition", path, offset)

    def type_definition(self, path: Path, offset: int) -> list[Span]:
        return self._locations("textDocument/typeDefinition", path, offset)

    def hover(self, path: Path, offset: int) -> str | None:
        """The hover text at `offset`, or None."""
        result = self._request("textDocument/hover", self._position(path, offset))
        if not result:
            return None
        contents = result.get("contents")
        if isinstance(contents, dict):
            return str(contents.get("value", ""))
        if isinstance(contents, list):
            return "\n".join(c if isinstance(c, str) else str(c.get("value", "")) for c in contents)
        return str(contents)
