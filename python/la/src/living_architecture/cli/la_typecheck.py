import os
import subprocess
import sys
from pathlib import Path

from deterministic_refactor.config.command import command_argv
from deterministic_refactor.contract.parser import parse
from deterministic_refactor.twin import FORWARDED_ENV
from living_architecture.contract import manifest, message


def la_typecheck(argv: list[str] | None = None) -> int:
    """The deprecated alias: `dr-typecheck` with the same arguments, after one deprecation line on stderr."""
    raw = command_argv(argv)
    parse("la-typecheck", raw, manifest())
    if os.environ.get(FORWARDED_ENV) != "1":
        print(message("typecheck-alias.deprecated"), file=sys.stderr, flush=True)
    dr_typecheck = Path(sys.argv[0]).resolve().parent / "dr-typecheck"
    return subprocess.run([str(dr_typecheck), *raw], check=False).returncode
