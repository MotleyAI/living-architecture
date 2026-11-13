## 1. Tests (pr-tests stage; failing until implemented)

- [ ] 1.1 `shared/vectors/format.yaml` `stamp`: replacement vectors with an existing `0.3.0` — plain first key, later
  key, `'0.3.0'` and `"0.3.0"` (→ bare), extra spaces and a tab after the colon kept, trailing comment kept, a quoted
  value containing `#`, no final line break, CRLF, after leading comments and `---`; `stamped: null` for a value on
  the next line, a block scalar, a flow mapping, `format : 0.3.0`, `'format': 0.3.0` and two `format:` lines. Update
  the section comment (insert or replace). Both twins' vector tests (`python/tests/test_vectors.py`,
  `node/test/vectors.test.ts`) run them; verify they fail on replacement.
- [ ] 1.2 Released-formats tests in both twins (`python/tests/test_format.py`, `python/tests/test_versions.py`,
  `node/test/format.test.ts`): the list is non-empty, versions, strictly ascending; the current format is its last
  entry and no newer than each package version and `plugin.json`.
- [ ] 1.3 Registry test in both twins (`python/tests/test_arch_migrate.py`, `node/test/migrate.test.ts`): each step
  declares `{source, target}`; exactly one unversioned step targeting `formats[0]`, one step per released format but
  the last, each targeting the next entry, no other source.
- [ ] 1.4 Chain tests in both twins with a fake two-step registry and a fake format list (injected through the
  migrate entry's parameters, never an env var): unversioned runs both steps; declaring the middle format runs only
  the second; an unreleased in-between format is refused naming it; the stamp is decided before any write (an
  unstampable config with a step that would write leaves the repo unchanged).
- [ ] 1.5 Rollback tests in both twins: a second step failing during planning, during verification and during
  application, after the first created, moved, deleted and replaced (non-default mode) files and removed a directory,
  restores bytes, modes and existence of every path and the config, and exits with the second step's message; a
  failed restore names the paths left changed; a failure on the config replacement restores the config.
- [ ] 1.6 Net-effect report tests in both twins: `a→b` prints only `moved a to b`; `a→b`, `b→c` prints `moved a to c`;
  `a→b`, `b→a` prints nothing; pre-existing `a→b` then delete `b` prints `deleted a`; create then delete prints
  nothing; rewrite then delete of a pre-existing path prints `deleted x`; a moved file a later step rewrites prints
  the move and `wrote` at its final path; temp files never appear; writes precede moves precede deletes, config last
  among writes.
- [ ] 1.7 Release-rule tests (`python/tests/test_release_scripts.py`, `python/tests/test_versions.py`) against
  temporary git repos with tags: formats unchanged passes; own version appended passes; another version, two
  versions, an edited or dropped entry fail naming both lists; a previous tag with only `format: 0.4.0` (also quoted,
  CRLF, with comments) reads as `[0.4.0]`; no `shared/config.yaml` at the tag reads as `[]`; an unrecognised file and
  a `git show` failure fail naming the release; the pre-tag `bump_problem` path applies the rule; the regex read of
  HEAD's `shared/config.yaml` equals its YAML read.
- [ ] 1.8 Conformance: re-bless `arch-migrate-format-unknown-older` (and any golden echoing the `la-arch-migrate` help)
  for the approved wordings — reason: deliberate wording change — only after 2.2 lands; no new case (design decision
  13).
- [ ] 1.9 Update existing tests that read the scalar `format` (`python/tests/test_conformance.py` `current_format`,
  `python/tests/test_format.py`, `python/tests/test_contract.py`'s manifest test for the help) to the last entry of
  `formats` / the approved help wording.
- [ ] 1.10 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. shared/

- [ ] 2.1 `config.yaml`: `format: 0.4.0` → `formats: [0.4.0]` with the approved comment (design.md).
- [ ] 2.2 `findings.yaml`: reword `arch-migrate.unknown-format` and `arch-migrate.stamp-mismatch`; `cli.yaml`: the
  approved `la-arch-migrate` help (exit map unchanged). Wordings verbatim from design.md.
- [ ] 2.3 `scripts/sync-shared`, then `scripts/sync-shared --check`; both `CONTRACT_HASH` files equal the shared hash
  (drift tests green).

## 3. Python twin

- [ ] 3.1 `contract/snapshot.py`: the released-formats accessor; `config/format.py`: current = last entry, the
  released list exposed, `stamp_format` inserts or replaces per design decision 8. Verify 1.1 and 1.2.
- [ ] 3.2 `c4/migrate.py`: the step registry (`{source, target, apply}`; the unversioned step = today's layout and
  arc42 conversion, never writing the config); the outer transaction (design decisions 1–3, 5) with the logical
  record and the net-effect report; the format flow (stamp decided first, unreleased older refused). Verify 1.3–1.6
  and the existing `arch-migrate-*` conformance cases unchanged.
- [ ] 3.3 `uv run pytest -q` (local test scope), `ruff check src tests`, `basedpyright src tests` green in `python/`.

## 4. npm twin

- [ ] 4.1 `node/src/contract/snapshot.ts`, `node/src/config/format.ts`: as 3.1, comparison without `Number`.
- [ ] 4.2 `node/src/c4/migrate.ts`: as 3.2.
- [ ] 4.3 `npm run lint && npm run typecheck && npm test`, `npm run build && npm run conformance`, and
  `scripts/conformance-cross` on the `arch-migrate-*` and `format-*` cases green.

## 5. Release rule

- [ ] 5.1 `scripts/release_rule.py`: read a release's formats (`formats`, else `[format]`, else `[]` when absent via
  `git cat-file -e`; fail closed otherwise) with a strict one-line regex; the formats rule inside the `bump_problem`
  path, so `scripts/release-check` and the pre-tag test apply it. Verify 1.7.

## 6. Skill and docs

- [ ] 6.1 `plugin/skills/pr/SKILL.md` preflight: the approved replacement wording verbatim (design.md).
- [ ] 6.2 `docs/development.md` releasing sentence (approved); `docs/configuration.md`, `docs/how-it-works.md` and the
  `la-arch-migrate` line in `docs/commands.md` name the step-by-step conversion of an older released format.
- [ ] 6.3 `la-arch-check` green from either twin and `npx -y @anthropic-ai/claude-code plugin validate plugin`.
