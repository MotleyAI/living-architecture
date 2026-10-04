## Context

OS errors surface through two contract templates, `arch-check.setup-error` (`arch_check: {error}`) and
`arch-diagrams.error` (`la-arch-diagrams: {error}`), plus the Python-only conventions gate's `[unreadable]`
finding. The Python twin fills `{error}` with `str(OSError)`; the npm twin fakes the same text via a
hard-coded errno table. Invalid-YAML and config errors already pass library wording through, with
`contains:` goldens noting "wording is not part of the contract".

## Goals / Non-Goals

**Goals:** no twin imitates another runtime's error wording; both twins fail on the same inputs with the same
exit code and a message naming the offending path; no errno numbers in goldens.

**Non-Goals (user decision):** byte-identical OS/YAML error text across twins; per-errno `findings.yaml`
templates or mapping tables; repo-relative paths in OS error messages; YAML error templates.

## Decisions

- **Passthrough, not mapping.** Each twin passes its runtime's message into the existing template. Chosen over
  a single generic template and over the issue's per-errno templates for simplicity, and because it follows
  the corpus's existing treatment of YAML/config wording. Principle 2 is satisfied: the contract supplies the
  text the tool authors (the prefix); the runtime detail is data, as with YAML library messages.
- **Goldens assert exit + prefix + path.** The path appears in both runtimes' messages (Python: `'<path>'`,
  Node: `open '<path>'`), so `contains:` on the `<ROOT>`-normalized absolute path holds in both twins.
  Exception: Node's EISDIR message (`EISDIR: illegal operation on a directory, read`) carries no path, so
  `arch-diagrams-doc-is-directory` asserts exit + prefix only.
- **One new non-not-found case** (`arch-diagrams-doc-is-directory`, neutral) so a second OS error kind is
  exercised through both twins. Codex flagged that Node's `readFileSync` on a directory may not throw on
  FreeBSD; rejected, as FreeBSD is not a supported platform (Linux and macOS both raise `EISDIR`).
- **Conventions gate converted now** (`conventions-unreadable-directory` → `contains:`) so the gate's later
  twinning inherits no errno golden.

## Risks / Trade-offs

- `contains:` goldens pin less than byte goldens: a regression in the wording around the path would go
  unnoticed. Accepted; the exit code, prefix and path are the behaviour that matters.
