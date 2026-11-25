"""Generate MODIFIED/RENAMED spec deltas for the dr -> trmv rename from the corpus."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])

RULES = [
    (r"docs/deterministic-refactoring\.md", "docs/rename-and-move.md"),
    (r"\bdr:deterministic-refactor\b", "trmv:rename-move"),
    (r"skills/deterministic-refactor\b", "skills/rename-move"),
    (r"deterministic-refactor\.schema\.json", "trmv.schema.json"),
    (r"deterministic-refactor\.yaml", "trmv.yaml"),
    (r"deterministic_refactor", "trmv"),
    (r"deterministic-refactor", "type-rename-move"),
    (r"[Dd]eterministic refactoring", "verified renames and moves"),
    (r"\bDR_", "TRMV_"),
    (r"\bDr(?=[A-Z])", "Trmv"),
    (r"\bdr(?=[A-Z_./:-])", "trmv"),
    (r"\bdr\b", "trmv"),
]
LEFT = re.compile(r"\bdr\b|\bdr[_./-]|\bDR_|\b[dD]r[A-Z]|deterministic[-_ ]refactor")


def sub_line(line: str) -> str:
    for pattern, repl in RULES:
        line = re.sub(pattern, repl, line)
    return line


def sub(text: str) -> str:
    """Substitute every line but scenario titles, which a delta cannot rename (renamed at archive time)."""
    return "\n".join(l if l.startswith("#### Scenario:") else sub_line(l) for l in text.split("\n"))


def blocks(text: str):
    """(header line, block text) per requirement."""
    parts = re.split(r"(?m)^(?=### Requirement: )", text)
    for part in parts[1:]:
        body = re.split(r"(?m)^(?=## )", part)[0]
        yield part.splitlines()[0], body.rstrip() + "\n"


total = 0
for spec in sorted((ROOT / "openspec/specs").glob("*/spec.md")):
    modified, renamed = [], []
    for header, body in blocks(spec.read_text()):
        new = sub(body)
        if new == body:
            continue
        new_header = new.splitlines()[0]
        if new_header != header:
            renamed.append(f"- FROM: `{header}`\n- TO: `{new_header}`\n")
        modified.append(new)
        for line in new.splitlines():
            if LEFT.search(line) and not line.startswith("#### Scenario:"):
                print(f"LEFT {spec.parent.name}: {line[:160]}")
    if not modified:
        continue
    total += len(modified)
    out = []
    if renamed:
        out.append("## RENAMED Requirements\n\n" + "\n".join(renamed))
    out.append("## MODIFIED Requirements\n\n" + "\n".join(modified))
    target = OUT / spec.parent.name / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out))
    print(f"{spec.parent.name}: {len(modified)} modified, {len(renamed)} renamed")
print("total", total)
