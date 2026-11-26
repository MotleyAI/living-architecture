import os
import subprocess
import sys
from pathlib import Path

from living_architecture.contract import manifest, message
from trmv.config.command import command_argv
from trmv.contract.parser import parse
from trmv.twin import FORWARDED_ENV


def la_typecheck(argv: list[str] | None = None) -> int:
    """The deprecated alias: `trmv-typecheck` with the same arguments, after one deprecation line on stderr."""
    raw = command_argv(argv)
    parse("la-typecheck", raw, manifest())
    if os.environ.get(FORWARDED_ENV) != "1":
        print(message("typecheck-alias.deprecated"), file=sys.stderr, flush=True)
    trmv_typecheck = Path(sys.argv[0]).resolve().parent / "trmv-typecheck"
    return subprocess.run([str(trmv_typecheck), *raw], check=False).returncode
