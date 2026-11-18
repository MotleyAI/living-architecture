"""Published files carry no private names, projects, issue keys, or local paths."""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
THIS_FILE = Path(__file__).resolve()

BLOCKED = re.compile(r"\begor\b|\bjames\b|slayer|motley|\bdev-\d+|/home/", re.IGNORECASE)
# The publisher may appear only as the copyright holder, author/owner, and in the repo URL.
PUBLISHER_ALLOWED = (
    "Copyright (c) 2026 MotleyAI",
    'authors = [{ name = "MotleyAI" }]',
    '"name": "MotleyAI"',
    "MotleyAI/living-architecture",
)
README_COPIES = ("README.md", "python/README.md")
# Per file: the maintainer only as the packages' maintainer, the project that uses the plugin only as the README's
# links to it and to its example principles document.
FILE_ALLOWED = {
    "python/pyproject.toml": ('maintainers = [{ name = "Egor Kraev" }]',),
    "node/package.json": ('"maintainers": [\n    "Egor Kraev"\n  ]',),
    **{
        readme: (
            "[SLayer](https://github.com/MotleyAI/slayer)",
            "(https://github.com/MotleyAI/slayer/blob/main/architecture/sql.arc42.md)",
        )
        for readme in README_COPIES
    },
}


# OpenSpec change folders (active and archived) keep their issue references.
CHANGE_DOCS = "openspec/changes/"


def _published_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [REPO_ROOT / rel for rel in listing if (REPO_ROOT / rel).is_file() and not rel.startswith(CHANGE_DOCS)]


def _violations(text: str, rel: str = "") -> list[str]:
    for allowed in (*PUBLISHER_ALLOWED, *FILE_ALLOWED.get(rel, ())):
        text = text.replace(allowed, "")
    return sorted({m.group(0) for m in BLOCKED.finditer(text)})


def test_blocklist_catches_the_real_cases():
    assert _violations("see DEV-1234 and dev-9") == ["DEV-1234", "dev-9"]
    assert _violations("Motley's SLayer at /home/x") == ["/home/", "Motley", "SLayer"]
    assert _violations("Categories, Egor") == ["Egor"]
    assert _violations("Copyright (c) 2026 MotleyAI") == []
    assert _violations("the [SLayer](https://github.com/MotleyAI/slayer) codebase, SLayer", "README.md") == ["SLayer"]
    assert _violations('maintainers = [{ name = "Egor Kraev" }], Egor', "python/pyproject.toml") == ["Egor"]


def test_file_exemptions_hold_only_in_their_own_file():
    link = "[SLayer](https://github.com/MotleyAI/slayer)"
    maintainer = 'maintainers = [{ name = "Egor Kraev" }]'
    assert _violations(link, "docs/commands.md") == ["Motley", "SLayer", "slayer"]
    assert _violations(maintainer, "README.md") == ["Egor"]
    assert set(FILE_ALLOWED) <= {p.relative_to(REPO_ROOT).as_posix() for p in _published_files()}


def test_change_docs_are_exempt_but_specs_are_not():
    published = {p.relative_to(REPO_ROOT).as_posix() for p in _published_files()}
    assert not any(rel.startswith(CHANGE_DOCS) for rel in published)
    assert "openspec/config.yaml" in published


def test_no_blocked_terms_in_published_files():
    offenders = {}
    for path in _published_files():
        if path.resolve() == THIS_FILE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = _violations(text, path.relative_to(REPO_ROOT).as_posix())
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert offenders == {}
