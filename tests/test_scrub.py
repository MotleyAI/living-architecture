"""Published files carry no private names, projects, issue keys, or local paths."""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
THIS_FILE = Path(__file__).resolve()

BLOCKED = re.compile(r"\begor\b|\bjames\b|slayer|motley|\bdev-\d+|/home/", re.IGNORECASE)
# The publisher may appear only as the copyright holder, author/owner, and in the repo URL.
PUBLISHER_ALLOWED = (
    "Copyright (c) 2026 MotleyAI",
    'authors = [{ name = "MotleyAI" }]',
    '"name": "MotleyAI"',
    "MotleyAI/living-architecture",
)


def _published_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [REPO_ROOT / rel for rel in listing if (REPO_ROOT / rel).is_file()]


def _violations(text: str) -> list[str]:
    for allowed in PUBLISHER_ALLOWED:
        text = text.replace(allowed, "")
    return sorted({m.group(0) for m in BLOCKED.finditer(text)})


def test_blocklist_catches_the_real_cases():
    assert _violations("see DEV-1234 and dev-9") == ["DEV-1234", "dev-9"]
    assert _violations("Motley's SLayer at /home/x") == ["/home/", "Motley", "SLayer"]
    assert _violations("Categories, Egor") == ["Egor"]
    assert _violations("Copyright (c) 2026 MotleyAI") == []


def test_no_blocked_terms_in_published_files():
    offenders = {}
    for path in _published_files():
        if path.resolve() == THIS_FILE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = _violations(text)
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert offenders == {}
