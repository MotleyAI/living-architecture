"""A stand-in LSP server for the language-server session tests: `fake_lsp_server.py <mode> <record.jsonl>`.

Modes: `ok`; `fail-start` (exits before reading); `unpatched` (records no patch result); `exit-on-query` (exits at
the first query). Queries echo their position back as a three-unit range; hover answers `(variable) x: Unknown`.
"""

import json
import os
import sys

MODE, RECORD = sys.argv[1], sys.argv[2]
ENV_KEYS = ("PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "NODE_OPTIONS", "LA_PYRIGHT_PATCH_RESULT")
QUERIES = ("textDocument/references", "textDocument/definition", "textDocument/typeDefinition", "textDocument/hover")


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


def main() -> None:
    if MODE == "fail-start":
        sys.exit(1)
    record({"cwd": os.getcwd(), "env": {k: os.environ.get(k) for k in ENV_KEYS}})
    while True:
        msg = read()
        method = msg.get("method")
        if method == "initialize":
            if MODE != "unpatched":
                with open(os.environ["LA_PYRIGHT_PATCH_RESULT"], "w", encoding="utf-8") as fh:
                    json.dump({"outcome": "patched", "version": "1.40.2", "count": 1}, fh)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"capabilities": {}}})
        elif method == "initialized":
            send({"jsonrpc": "2.0", "id": "cfg", "method": "workspace/configuration",
                  "params": {"items": [{"section": "python"}, {"section": "basedpyright.analysis"}]}})
            reply = read()
            record({"configuration": reply.get("result")})
        elif method == "textDocument/didOpen":
            record({"opened": msg["params"]["textDocument"]["uri"]})
        elif method in QUERIES:
            if MODE == "exit-on-query":
                sys.exit(3)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": answer(msg)})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
        elif method == "exit":
            sys.exit(0)


main()
