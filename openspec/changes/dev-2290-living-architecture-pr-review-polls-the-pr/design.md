## Context

See proposal.md (Why). `la-wait-for-reviews` (`shared/scripts/wait-for-reviews.sh`, run by both twins as a passthrough)
runs Stage 0a (gate over the rollup + HEAD's Sonar suites, 60 s poll) then Stage 0b (CodeRabbit settle, 30 s poll,
10 min cap) and prints progress on stdout. The skills arm it with the Claude Code Monitor tool, which wakes the agent
on every stdout line and expires after at most 30 minutes. `pr-review` treats a sweep as blocking on the exit.

Symptom: early feedback waits for the slowest source. Structural cause: the watcher reports only a whole-gate verdict,
so which items are new lives in agent memory, which compaction, a session end or a Monitor expiry erases; "triage once
per HEAD" cannot be enforced. Fix: the tool emits deduped, persisted per-item events, one code path for every source.

Applicable principles (`architecture/system.arc42.md`): P1 twins (shared script; neutral conformance cases), P2
(help texts in `shared/cli.yaml`; event lines are the shared script's), P4 (no target-repo code runs). No arc42 or
model edit. Both capabilities already attach to `python.review` (`review-detection`, `failed-pr-checks`).

## Goals / Non-Goals

**Goals:** per-item events on stdout, deduped across runs; one poll loop; a `--check` filter so each `ci-failed`
event fetches only its own log; skills that triage and fix as events arrive and push once per sweep.

**Non-Goals:** the re-triggered rate limit (DEV-2245); a fresh PR's bots declared too early (DEV-2226); the release
and version bump; tests of skill prose.

## Decisions

1. **The watcher emits deduped per-item events; no skill-only polling** (default). Skill-only polling keeps the
   dedupe in agent memory, the class that causes the bug.
2. **Printed keys persist per PR in the per-worktree git dir, recorded on emit** (user). Rejected: a stateless
   watcher plus a Monitor-tailed log (process management in skill prose; a crash re-emits everything). Rejected
   (user, Codex finding 1): recording on triage via an `--ack` call — a second writer and an agent duty, plus
   duplicate wake-ups on every re-arm; an item emitted just before a session dies is caught by the end-of-sweep
   full fetch.
3. **CodeRabbit items keyed by comment / review id only; edits are not items** (user). Edits are mostly "Addressed"
   stamps; the end-of-sweep full fetch catches a substantive rewrite. Rejected (codex, finding 2): keying on
   `updated_at`, for the same reason.
4. **One poll loop at `LA_WAIT_POLL_SECONDS`; the hard-coded 30 s CodeRabbit poll is dropped** (user). Costs up to
   30 s settle latency when CodeRabbit is the last source; the `LA_WAIT_CR_SETTLE` cap counts from gate-clear.
5. **Progress to stderr, events to stdout, always on, no flag** (default). Monitor wakes only on stdout; a flag would
   make two modes for one consumer. Every existing `shim-wait-for-reviews-*` golden is re-blessed for it.
6. **Exit 3 deferred until the checks are terminal** (default). Matches today, where Stage 0b ran after gate-clear;
   convergence and the archive gate are unchanged.
7. **`la-fetch-failed-pr-checks --check X`, matching Details URL or name** (default; codex, finding 3). The event
   carries the Details URL when there is one; a name alone is ambiguous across workflows.
8. **CI dedupe key** (codex, finding 3): CheckRun / WorkflowRun = SHA + Details URL (a re-run has a new job URL),
   else SHA + name; StatusContext = SHA + context + `startedAt`, else SHA + context + Details URL.
9. **State writes re-read, union and rename atomically; no locking** (codex, finding 4). Overlapping watchers can at
   worst print an item twice, never lose one.
10. **`coderabbit-settled` keyed by SHA + outcome** (user). A rate limit then a review on the same HEAD prints both,
    so the stream ends on the outcome the exit reflects.
11. **CodeRabbit and Sonar checks never produce `ci-failed`; CodeRabbit issue comments are not items** (default).
    They have their own events or are not findings.
12. **Standalone `process-reviews` uses the same watch; its plan waits for the exit** (default).
13. **Rejected (codex, finding 5): end-to-end skill tests.** Skill prose is not executable and is never pinned by
    tests; the watcher's boundaries are conformance cases.
14. **Help texts** (user, approved wording), in `shared/cli.yaml`:
    - `la-wait-for-reviews`: "Watch a PR until CodeRabbit, Sonar and CI are terminal, printing each new failed check, CodeRabbit comment and finished Sonar analysis once (bundled script)."
    - `la-fetch-failed-pr-checks` usage line: "  --check NAME          only the failed check named NAME" (the matching widened to Details URL or name by decision 7; the usage line is otherwise as approved)
15. **`process-reviews` skill edits** (user, approved wording):
    - Frontmatter description: replace "First waits (polling every 1 min, max 30 min) until CodeRabbit, Sonar, and every CI check on the PR are in a terminal state — while a Codex review runs concurrently against the local diff. Then fetches" with "Watches the PR every minute (30 min cap) and triages each new failed CI check, CodeRabbit comment and finished Sonar analysis as it appears, while a Codex review runs concurrently against the local diff. Once everything is terminal, fetches".
    - Step 0 heading: "### 0. Watch the PR (and kick off Codex in parallel)".
    - Its first paragraph ("Don't fetch anything until every status check…") becomes: "Triage each source as soon as it reports, never a source that is still running: mid-flight CodeRabbit, Sonar or CI output is incomplete."
    - In the Codex paragraph: "arms the gate-wait Monitor" → "arms the watch Monitor"; "By the time the gate clears" → "By the time the watch exits".
    - `#### 0a + 0b` retitled "Watch status checks + CodeRabbit"; its code block and exit sentence replaced by:

      > Arm `la-wait-for-reviews <PR>` with the Monitor tool (`timeout_ms` at its maximum). It polls the PR every minute and prints one stdout line per new item, never the same item twice, even across runs:
      >
      > - `ci-failed <sha> <url> <check>`: a check on HEAD failed;
      > - `coderabbit-comment <url>` / `coderabbit-review <url>`: a new CodeRabbit thread, reply, or review body;
      > - `sonar-done <sha> <conclusion>`: HEAD's Sonar analysis finished;
      > - `coderabbit-settled <sha> <outcome>`: reviewed, carried-forward, rate-limited, paused, or cap;
      > - `head-moved <old> <new>`.
      >
      > On each event, run Steps 1–4 for that item alone, at once: `la-fetch-failed-pr-checks <PR> --check <check>` for a failed check, `la-fetch-coderabbit-threads <PR>` for a CodeRabbit item (triage only the named comment or review), the Sonar calls of Step 1 for `sonar-done`. If the Monitor expires before the command exits, re-arm the same command; it prints only what is new.
      >
      > It exits 0 when every check on HEAD is terminal and CodeRabbit has settled on HEAD (or is not on the PR, or the 10-minute settle cap after the checks finish ran out), 1 if the checks do not finish within 30 minutes, and 3 when CodeRabbit was rate limited or paused on HEAD, once the checks finish.

      (`<check>` is the event's URL when it has one, else its name, per decision 7.)
    - The "Reviewed / Carried forward / Rate limited" bullets keep "(exit 0)" / "(exit 3)"; "Anything else: keep polling until the cap." stays.
    - The paragraph "**Don't idle while the script runs.** …" through "…re-fetch CodeRabbit to pick up late threads." is replaced by: "Only Step 5, the fix plan, waits for the command to exit, so the plan covers every source. When it exits, run Step 1 for every source once more and triage whatever no event named: edited CodeRabbit comments, and older threads that need a reply."
    - "Once the script exits, finish Step 1 for any source not yet fetched." is deleted.
16. **`pr-review` skill edits** (user, approved wording):
    - Step 1 loop item 1: "1. **Initial full sweep.** Run `/la:process-reviews` on the current pushed HEAD. Fix each valid item in the working tree as soon as it is triaged, while the watch keeps running; push nothing. Run every local gate. When the watch exits, the failing set is complete."
    - Item 2 gains: "Run the local gates on these fixes as you go; the full convergence, Codex included, runs once the watch has exited."
    - Item 4: "4. **Full remote sweep.** Run `/la:process-reviews` again on the new HEAD (it also re-runs Codex), fixing each valid item as it is triaged, without pushing, until its watch exits. Any new failure sends you back to step 2, then step 3. Repeat until one full push cycle returns every source green with nothing left to fix."
    - "Green" paragraph: "`la-wait-for-reviews` printing \"gate clear\" only means" → "`la-wait-for-reviews` exiting 0 only means".
    - "Use `/la:process-reviews` for the remote sweeps" paragraph: "it owns the wait-for-settle + fetch" → "it owns the watch + fetch"; "(its gate-poll is about remote state…)" → "(its watch is about remote state…)".

## Risks / Trade-offs

- [An item printed just before a session dies is not printed again] → the end-of-sweep full fetch triages it.
- [Two watchers on one PR may print an item twice] → atomic union writes; a duplicate costs one triage pass.
- [A Monitor expiry mid-sweep] → re-arm the same command; the state file makes it print only new items.
- [Golden churn] → every `shim-wait-for-reviews-*` golden is re-blessed once, with the reason in the commit message.
