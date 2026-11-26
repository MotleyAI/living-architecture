"""The stealth merge-base baseline cache: its key and its entries under the trmv stealth directory."""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path

from trmv.contract import is_regular_file, language


def cache_key(*, commit: str, language: str, command: str, version: str, fingerprints: dict[str, bytes]) -> str:
    """The hex sha256 of the merge-base commit, the language, the checker command, the trmv version and each fingerprint
    file's name and content digest, in code-point order of name."""
    fields = [commit, language, command, version]
    for name in sorted(fingerprints):
        fields += [name, hashlib.sha256(fingerprints[name]).hexdigest()]
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def fingerprints(root: Path, lang_id: str) -> dict[str, bytes]:
    """The contents of the language's fingerprint files that exist at `root`."""
    out: dict[str, bytes] = {}
    for name in language(lang_id)["fingerprint_files"]:
        with contextlib.suppress(OSError):
            if is_regular_file(root / name):
                out[name] = (root / name).read_bytes()
    return out


def read_entry(path: Path) -> str | None:
    """A cached baseline's text, None when absent or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write_entry(path: Path, text: str) -> None:
    """Store a baseline's text whole or not at all; a failure only costs the next run a recomputation."""
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(text)
            os.replace(name, path)
        except OSError:
            Path(name).unlink(missing_ok=True)
