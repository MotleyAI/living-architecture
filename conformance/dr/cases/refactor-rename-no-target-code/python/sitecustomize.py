import pathlib
import sys

# basedpyright's interpreter probes run `python -c`; la's own process, which PYTHONPATH also reaches, does not.
if sys.argv[:1] == ['-c']:
    pathlib.Path(__file__).with_name('MARKER').write_text('ran')
