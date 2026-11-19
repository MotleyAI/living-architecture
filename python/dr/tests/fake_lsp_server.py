"""A stand-in LSP server for the language-server session tests: `fake_lsp_server.py <mode> <record.jsonl>`.

Modes: `ok`; `fail-start` (exits before reading); `unpatched` (records no patch result); `exit-on-query` (exits at
the first query); `error-on-initialize` (answers `initialize` with an error, after a line on stderr); `no-export`
(answers the export command with an error); `export-null` (answers it with null); `export-unverified` (records an
unverified export preload); `bad-range` (exports ranges one unit too long). Queries echo their position back as a
three-unit range; hover answers `(variable) x: Unknown`; the export answers every whole-word occurrence of each
requested name in the opened texts, as `name` occurrences with no declaration.
"""

import json
import os
import re
import sys

MODE, RECORD = sys.argv[1], sys.argv[2]
ENV_KEYS = (
    "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONPATH", "NODE_OPTIONS",
    "LA_PYRIGHT_PATCH_RESULT", "LA_PYRIGHT_EXPORT_RESULT",
)
QUERIES = ("textDocument/references", "textDocument/definition", "textDocument/typeDefinition", "textDocument/hover")
EXPORT = "la.exportOccurrences"
TEXTS: dict[str, str] = {}


def record(entry: dict) -> None:
    with open(RECORD, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def read() -> dict:
    length = 0
    while (line := sys.stdin.buffer.readline()) not in (b"\r\n", b""):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    if not length:
        sys.exit(0)
    return json.loads(sys.stdin.buffer.read(length))


def send(payload: dict) -> None:
    body = json.dumps(payload).encode()
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    sys.stdout.buffer.flush()


def answer(msg: dict) -> object:
    pos = msg["params"]["position"]
    if msg["method"] == "textDocument/hover":
        return {"contents": {"kind": "plaintext", "value": "(variable) x: Unknown"}}
    end = {"line": pos["line"], "character": pos["character"] + 3}
    return [{"uri": msg["params"]["textDocument"]["uri"], "range": {"start": pos, "end": end}}]


def position(text: str, index: int) -> dict:
    """The LSP position of a character index: lines end at CRLF, CR or LF; columns count UTF-16 units."""
    line, start = 0, 0
    for m in re.finditer(r"\r\n|\r|\n", text):
        if m.end() > index:
            break
        line, start = line + 1, m.end()
    return {"line": line, "character": sum(2 if ord(c) > 0xFFFF else 1 for c in text[start:index])}


def export(request: dict) -> dict:
    occurrences = []
    for uri in request.get("files", []):
        text = TEXTS.get(uri, "")
        for name in request.get("names", []):
            for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text):
                end = position(text, m.end())
                if MODE == "bad-range":
                    end = {**end, "character": end["character"] + 1}
                occurrences.append({"uri": uri, "range": {"start": position(text, m.start()), "end": end},
                                    "name": name, "kind": "name", "declarations": [], "receiver": None})
    return {"occurrences": occurrences}


def execute(msg: dict) -> None:
    params = msg["params"]
    record({"command": params["command"], "arguments": params.get("arguments")})
    if params["command"] != EXPORT or MODE == "no-export":
        send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": 1, "message": "Unsupported command"}})
    elif MODE == "export-null":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
    else:
        send({"jsonrpc": "2.0", "id": msg["id"], "result": export((params.get("arguments") or [{}])[0])})


def initialize(msg: dict) -> None:
    if MODE != "unpatched":
        with open(os.environ["LA_PYRIGHT_PATCH_RESULT"], "w", encoding="utf-8") as fh:
            json.dump({"outcome": "patched", "version": "1.40.2", "count": 1}, fh)
    if os.environ.get("LA_PYRIGHT_EXPORT_RESULT"):
        outcome = "unverified" if MODE == "export-unverified" else "patched"
        with open(os.environ["LA_PYRIGHT_EXPORT_RESULT"], "w", encoding="utf-8") as fh:
            json.dump({"outcome": outcome, "version": "1.40.2"}, fh)
    send({"jsonrpc": "2.0", "id": msg["id"], "result": {"capabilities": {}}})


def main() -> None:
    if MODE == "fail-start":
        sys.exit(1)
    record({"cwd": os.getcwd(), "env": {k: os.environ.get(k) for k in ENV_KEYS}})
    while True:
        msg = read()
        method = msg.get("method")
        if method == "initialize" and MODE == "error-on-initialize":
            sys.stderr.write("fake: initialize failed\n")
            sys.stderr.flush()
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": "fake failure"}})
        elif method == "initialize":
            initialize(msg)
        elif method == "initialized":
            send({"jsonrpc": "2.0", "id": "cfg", "method": "workspace/configuration",
                  "params": {"items": [{"section": "python"}, {"section": "basedpyright.analysis"}]}})
            reply = read()
            record({"configuration": reply.get("result")})
        elif method == "textDocument/didOpen":
            document = msg["params"]["textDocument"]
            TEXTS[document["uri"]] = document["text"]
            record({"opened": document["uri"]})
        elif method == "textDocument/didChange":
            TEXTS[msg["params"]["textDocument"]["uri"]] = msg["params"]["contentChanges"][-1]["text"]
        elif method == "workspace/executeCommand":
            execute(msg)
        elif method in QUERIES:
            if MODE == "exit-on-query":
                sys.exit(3)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": answer(msg)})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
        elif method == "exit":
            sys.exit(0)


main()
