"""The stealth waiver ledger: waivers kept outside the repo, matched by path, rule and trimmed line text."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import conventions, message, schema, validate
from trmv.config import ConfigError, parse_config
from trmv.contract import os_error_text


class LedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    rule: str
    line: str
    reason: str


def _invalid(path: Path, error: str) -> ConfigError:
    return ConfigError(message("conventions.ledger-invalid", path=str(path), error=error))


def load_ledger(path: Path) -> list[LedgerEntry]:
    """The ledger's entries; none when it is missing. ConfigError naming the file when it is not a valid ledger."""
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise _invalid(path, os_error_text(exc, path.parent, path)) from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(message("yaml.invalid", path=str(path))) from exc
    data = parse_config(text, str(path))
    data = [] if data is None else data
    errors = validate(schema("waiver-ledger"), data)
    if errors:
        raise _invalid(path, "; ".join(errors))
    rules = conventions()["rules"]
    for index, entry in enumerate(data):
        if not rules.get(entry["rule"], {}).get("waivable"):
            raise _invalid(path, message("conventions.ledger-rule", index=index, rule=entry["rule"]))
    return [LedgerEntry.model_validate(entry) for entry in data]


def waived(entries: list[LedgerEntry], *, path: str, rule: str, line: str) -> bool:
    """Whether an entry waives the violation of `rule` on `line` of `path`."""
    text = line.removesuffix("\r").strip()
    return any(e.path == path and e.rule == rule and e.line == text for e in entries)
