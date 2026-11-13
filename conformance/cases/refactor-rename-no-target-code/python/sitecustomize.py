import pathlib

pathlib.Path(__file__).with_name('MARKER').write_text('ran')
