import subprocess
import sys

import pytest
from rope.refactor import patchedast

from deterministic_refactor.rope_patches import apply_rope_patches

SIGNATURES = [
    'def f(*, m: str = "(host)"):\n    pass\n',
    'def f(a, /, b="(", *args, c=")", **kw):\n    pass\n',
    'def f(a, /):\n    pass\n',
    'def f(*args, k=1):\n    pass\n',
]


@pytest.mark.parametrize("source", SIGNATURES)
def test_patched_walker_handles_full_signature_grammar(source: str) -> None:
    apply_rope_patches()
    patchedast.get_patched_ast(source, sorted_children=True)


def test_unpatched_rope_still_needs_the_patch() -> None:
    # Canary: once rope fixes this upstream, the patch can be dropped.
    code = (
        "from rope.refactor import patchedast\n"
        f"patchedast.get_patched_ast({SIGNATURES[0]!r}, sorted_children=True)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "MismatchedTokenError" in result.stderr
