"""`la-arch-scaffold`: a starter model, views and arc42 from the measured top-level units and import edges."""

from __future__ import annotations

import contextlib
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from living_architecture import twin
from living_architecture.archcheck.facts import Facts, native_top_level_facts
from living_architecture.archcheck.index import (
    INDEX_REL,
    ArchCheckError,
    declared_languages,
    load_index,
    resolve_layout,
)
from living_architecture.archcheck.nodes import separator
from living_architecture.c4 import diagram_block, parse_model, parse_views, read_index
from living_architecture.contract import message

SPECIFICATION_REL = "architecture/model/specification.c4"
VIEWS_REL = "architecture/views.c4"
ARC42_REL = "architecture/system.arc42.md"

SPECIFICATION = """specification {
  element system
  element node
  element bucket {
    #virtual
  }
  tag legacy
  tag virtual
}
"""


def _model_rel(language: str) -> str:
    return f"architecture/model/{language}.c4"


def _existing_output(root: Path) -> str | None:
    """The first file the scaffold would clash with, repo-relative; None when the model is still unwritten."""
    arch = root / "architecture"
    candidates = [*sorted((arch / "model").glob("*.c4")), arch / "views.c4", *sorted(arch.glob("*.arc42.md"))]
    return next((p.relative_to(root).as_posix() for p in candidates if p.is_file()), None)


def node_id(unit: str, language: str) -> str:
    """The unit's last segment with non-identifier characters as `_`, prefixed `n_` when it starts with a digit."""
    ident = re.sub(r"\W", "_", unit.split(separator(language))[-1], flags=re.ASCII)
    return f"n_{ident}" if ident[:1].isdigit() else ident


def _ids(facts: Facts) -> dict[str, str]:
    ids: dict[str, str] = {}
    owners: dict[str, str] = {}
    for unit in facts.top_level_units:
        if "'" in unit:
            raise ArchCheckError(message("arch-scaffold.unquotable-unit", language=facts.language, unit=unit))
        ident = node_id(unit, facts.language)
        if ident in owners:
            raise ArchCheckError(
                message("arch-scaffold.id-collision", language=facts.language, first=owners[ident], second=unit, id=ident)
            )
        owners[ident] = unit
        ids[unit] = ident
    return ids


def _render_model(facts: Facts) -> str:
    ids = _ids(facts)
    lines = ["model {", f"  {facts.language} = system '{facts.language}' {{"]
    for unit in facts.top_level_units:
        title = unit.split(separator(facts.language))[-1]
        lines += [
            f"    {ids[unit]} = node '{title}' {{",
            "      metadata {",
            f"        package '{unit}'",
            "      }",
            "    }",
        ]
    if facts.edges:
        lines.append("")
        lines += [f"    {ids[edge.src]} -> {ids[edge.dst]}" for edge in facts.edges]
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def _render_views(languages: list[str]) -> str:
    lines = ["views {"]
    for language in languages:
        lines += [f"  view {language} of {language} {{", f"    title '{language}'", "    include *", "  }"]
    lines.append("}")
    return "\n".join(lines) + "\n"


def _index_text(root: Path, index: dict[str, Any], languages: list[str]) -> str:
    text = (root / INDEX_REL).read_bytes().decode("utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    if "legacy_arrows" not in index:
        text += "legacy_arrows: {baseline: 0}\n"
    if "diagrams" not in index:
        text += f"diagrams:\n  {ARC42_REL}: [{', '.join(languages)}]\n"
    return text


def _arc42(files: dict[str, str], languages: list[str]) -> str:
    """The arc42 skeleton with each view's diagram, rendered from the scaffold's own model and views."""
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for rel, text in files.items():
            (staging / rel).parent.mkdir(parents=True, exist_ok=True)
            (staging / rel).write_text(text, encoding="utf-8")
        model = parse_model(staging)
        views = parse_views(root=staging, model=model)
    by_id = {view.id: view for view in views.views}
    blocks = "\n\n".join(diagram_block(by_id[language], model) for language in languages)
    return f"{message('arch-scaffold.arc42-head')}\n{blocks}\n\n{message('arch-scaffold.arc42-tail')}"


def _facts(root: Path, index: dict[str, Any], language: str) -> Facts:
    if language == twin.NATIVE_LANGUAGE:
        return native_top_level_facts(resolve_layout(root, index[language]), language)
    return Facts.model_validate(twin.request_facts(language, root, [], top_level=True))


def scaffold(root: Path) -> dict[str, str]:
    """Every scaffold output, repo-relative path -> text, in write order; ArchCheckError when one cannot be made."""
    usable = read_index(root)
    if isinstance(usable, str):
        raise ArchCheckError(usable)
    index = load_index(root)
    existing = _existing_output(root)
    if existing is not None:
        raise ArchCheckError(message("arch-scaffold.exists", path=existing))
    languages = declared_languages(index)
    files = {SPECIFICATION_REL: SPECIFICATION}
    for language in languages:
        files[_model_rel(language)] = _render_model(_facts(root, index, language))
    files[VIEWS_REL] = _render_views(languages)
    index_text = _index_text(root, index, languages)
    files[ARC42_REL] = _arc42({**files, INDEX_REL: index_text}, languages)
    files[INDEX_REL] = index_text
    return files


def write_scaffold(root: Path, files: dict[str, str]) -> None:
    """Write every output, creating all but the index exclusively; on an OSError undo the writes made so far, then re-raise."""
    index = root / INDEX_REL
    index_before = index.read_bytes().decode("utf-8")
    new_dirs = sorted({(root / rel).parent for rel in files if not (root / rel).parent.exists()}, key=lambda d: -len(str(d)))
    touched: list[Path] = []
    try:
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if path == index:
                touched.append(path)
                path.write_text(text, encoding="utf-8", newline="")
                continue
            with path.open("x", encoding="utf-8", newline="") as out:
                touched.append(path)
                out.write(text)
    except OSError:
        for path in touched:
            with contextlib.suppress(OSError):
                if path == index:
                    path.write_text(index_before, encoding="utf-8", newline="")
                else:
                    path.unlink()
        for directory in new_dirs:
            with contextlib.suppress(OSError):
                directory.rmdir()
        raise


def run_scaffold(root: Path) -> int:
    """`la-arch-scaffold`: write the outputs and print each path, or exit 2 having written nothing."""
    try:
        files = scaffold(root)
        write_scaffold(root, files)
    except (ArchCheckError, twin.TwinError, OSError) as exc:
        print(message("arch-scaffold.error", error=str(exc)), file=sys.stderr)
        return 2
    except twin.RelayedFailure:
        return 2
    for rel in files:
        print(message("arch-scaffold.written", path=rel))
    return 0
