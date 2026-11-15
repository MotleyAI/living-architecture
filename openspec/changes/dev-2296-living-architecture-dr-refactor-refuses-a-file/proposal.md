## Why

The Python `dr-refactor` refuses a whole module with `refactor.rope-walk` when the module holds an f-string whose
text contains a triple quote, such as SLayer's `#!/bin/sh` trampoline line. Every rename whose old name appears in
that file refuses too, wherever the renamed symbol lives. rope guesses an f-string's delimiters by searching its text
for quote characters, so a quote run in the text is taken for the closing quote. rope's fix (python-rope/rope#844)
is unreleased.

## What Changes

- The rope walker patch reads every f-string's and t-string's opening and closing delimiters from Python's tokens,
  never from a search of its text, on every supported Python version.
- f-strings and t-strings whose text holds quote characters, triple quotes included, are refactored like any other
  code; `dr-compliance --select rope-walk` no longer lists them.
- A canary test pins that unpatched rope still mis-walks such an f-string, pointing at python-rope/rope#844.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: "Python refactors walk every source construct" lists f-strings and t-strings whose text holds quote
  characters, triple quotes included.

## Impact

- `python/src/living_architecture/refactor/rope_patches.py`: the f-string visitor.
- `python/tests/test_rope_patches.py`: corpus cases and a canary.
- Conformance cases `compliance-rope-walk-clean` and `refactor-rename-rope-walk-constructs` and their inventory rows.
- Python twin only; the npm twin hands Python files to it.
