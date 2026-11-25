"""trmv's conformance cases: each reproduces its goldens byte-for-byte."""

from __future__ import annotations

from pathlib import Path

import pytest

from conformance_runner import UPDATE, Variant, check_case, package_cases, selected_runs


@pytest.mark.parametrize(
    ("case_dir", "variant"), [pytest.param(c, v, id=i) for c, v, i in selected_runs(package_cases("trmv"))]
)
def test_case(case_dir: Path, variant: Variant, tmp_path: Path) -> None:
    problems = check_case(case_dir, tmp_path, update=UPDATE, variant=variant)
    assert not problems, "\n".join(problems)
