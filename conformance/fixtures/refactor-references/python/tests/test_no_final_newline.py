from pkg.sql.client import X
import os


def test_no_final_newline() -> None:
    assert X == 1 and os.sep