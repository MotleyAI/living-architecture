// `la-check-conventions`: the deterministic conventions gate over a change's source files, every language.
import { spawnSync } from 'node:child_process';
import { ConfigError, loadConfig } from '../config/index.js';
import { byCodePoint, conventions, fixed1, fnmatch, globMatch, language, languageIds, message } from '../contract/index.js';
import { collect, FactsError, type Facts, languageOf } from './facts.js';

const FAILURES = new Set(['unreadable', 'syntax-error']);

interface Violation {
  path: string;
  line: number;
  rule: string;
  message: string;
}

interface FileCounts {
  rel: string;
  text: number;
  total: number;
}

const out = (text: string): void => void process.stdout.write(`${text}\n`);
const err = (text: string): void => void process.stderr.write(`${text}\n`);

export function isTestFile(rel: string): boolean {
  const id = languageOf(rel);
  return id !== null && (language(id).test_globs as string[]).some((glob) => globMatch(glob, rel));
}

export function isExcluded(rel: string, patterns: string[]): boolean {
  return patterns.some((pattern) => fnmatch(rel, pattern));
}

/** `text` (the flagged line) carries the language's waiver comment for `rule`. */
export function waived({ text, rule, language: id }: { text: string; rule: string; language: string }): boolean {
  if (!conventions().rules[rule]?.waivable) return false;
  const prefix = (language(id).comment_prefix as string).replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  const m = new RegExp(prefix + (conventions().waiver as string), 'u').exec(text);
  return m !== null && m[1] === rule;
}

const present = (languages: (string | null)[]): string[] => languageIds().filter((id) => languages.includes(id));

/** Each present language's files label in language-id order, or the empty label. */
export function filesLabel(languages: (string | null)[]): string {
  const labels = present(languages).map((id) => language(id).files_label as string);
  return labels.length > 0 ? labels.join(message('conventions.label-separator')) : message('conventions.empty-label');
}

function waiverExamples(languages: (string | null)[]): string {
  const examples = present(languages).map((id) => message('conventions.waiver-example', { prefix: language(id).comment_prefix }));
  return examples.join(message('conventions.waiver-separator'));
}

const applies = (rule: string, testFile: boolean): boolean => testFile || !conventions().rules[rule].tests_only;

/** The entry's findings for the configured `rules`; a file error only when one of them applies to the file. */
function violations(entry: Facts, rules: string[]): Violation[] {
  const rel: string = entry.path;
  const testFile = isTestFile(rel);
  if (FAILURES.has(entry.status)) {
    if (!rules.some((rule) => applies(rule, testFile))) return [];
    return [{ path: rel, line: entry.line, rule: entry.status, message: entry.message }];
  }
  if (entry.status !== 'ok') return [];
  const id = languageOf(rel) ?? '';
  return (entry.detections as Facts[])
    .filter((d) => rules.includes(d.rule) && applies(d.rule, testFile) && !waived({ text: d.text, rule: d.rule, language: id }))
    .map((d) => ({ path: rel, line: d.line, rule: d.rule, message: message(d.message_id, d.values) }));
}

function git(args: string[], cwd: string): string {
  const proc = spawnSync('git', args, { cwd, maxBuffer: 1 << 30 });
  if (proc.status !== 0) {
    const detail = proc.stderr?.toString('utf8').trim() ?? '';
    throw new ConfigError(detail || message('conventions.git-failed', { args: args.join(' ') }));
  }
  return proc.stdout.toString('utf8');
}

/** Changed files with a known extension: merge-base committed diff plus working-tree edits, sorted. */
export function changedSourceFiles(baseRef: string, repoRoot: string): string[] {
  const found = new Set<string>();
  for (const target of [`${baseRef}...HEAD`, 'HEAD']) {
    for (const path of git(['diff', '--name-only', '-z', '--diff-filter=ACMR', target], repoRoot).split('\0')) {
      if (path && languageOf(path) !== null) found.add(path);
    }
  }
  return [...found].sort(byCodePoint);
}

/** `origin/<branch>` for --base, or for the PR's base branch; best-effort fetch first. */
export function resolveBaseRef(pr: string | null, repo: string | null, base: string | null, repoRoot: string): string {
  let branch = base;
  if (branch === null) {
    const cmd = ['pr', 'view', String(pr), '--json', 'baseRefName', '--jq', '.baseRefName', ...(repo ? ['--repo', repo] : [])];
    const proc = spawnSync('gh', cmd, { cwd: repoRoot, encoding: 'utf8' });
    branch = (proc.stdout ?? '').trim();
    if (proc.status !== 0 || !branch) throw new ConfigError(message('conventions.pr-base-unresolved', { pr }));
  }
  spawnSync('git', ['fetch', 'origin', branch, '--quiet'], { cwd: repoRoot, stdio: 'ignore' });
  const ref = `origin/${branch}`;
  git(['rev-parse', '--verify', '--quiet', ref], repoRoot);
  return ref;
}

const pct = (text: number, total: number): string => fixed1((100 * text) / total);

/** Print per-group ratios; true when any group exceeds the cap. */
function ratioReport(groups: Record<string, FileCounts[]>, capPct: number): boolean {
  let red = false;
  const cap = fixed1(capPct);
  for (const [group, files] of Object.entries(groups)) {
    const text = files.reduce((n, f) => n + f.text, 0);
    const total = files.reduce((n, f) => n + f.total, 0);
    if (!total) continue;
    const values = { group, pct: pct(text, total), text, total, cap };
    err(message('conventions.ratio', values));
    if ((100 * text) / total <= capPct) continue;
    red = true;
    out(message('conventions.ratio-over', values));
    const ranked = files.filter((f) => f.total).sort((a, b) => b.text / b.total - a.text / a.total);
    for (const f of ranked) out(message('conventions.ratio-file', { path: f.rel, pct: pct(f.text, f.total), text: f.text, total: f.total }));
  }
  return red;
}

/** Known-extension, non-exempt paths; explicit unknown ones are warned about, exempt ones listed. */
function select(rels: string[], explicit: boolean, excludes: string[]): string[] {
  const known = rels.filter((rel) => {
    const ok = languageOf(rel) !== null;
    if (!ok && explicit) err(message('conventions.unknown-extension', { path: rel }));
    return ok;
  });
  const exempt = known.filter((rel) => isExcluded(rel, excludes));
  if (exempt.length > 0) err(message('conventions.exempt', { paths: exempt.join(', ') }));
  return known.filter((rel) => !isExcluded(rel, excludes));
}

/** Violations of the configured `rules` in path order, the ratio groups, the summary and the verdict. */
function report(rels: string[], facts: Map<string, Facts>, capPct: number, rules: string[]): number {
  const found: Violation[] = [];
  const groups: Record<string, FileCounts[]> = { source: [], tests: [] };
  for (const rel of rels) {
    const entry = facts.get(rel) as Facts;
    found.push(...violations(entry, rules));
    if (entry.status === 'ok') groups[isTestFile(rel) ? 'tests' : 'source']?.push({ rel, text: entry.text_lines, total: entry.total_lines });
  }
  found.sort((a, b) => byCodePoint(a.path, b.path) || a.line - b.line || byCodePoint(a.rule, b.rule));
  for (const v of found) out(message('conventions.violation', { ...v }));
  const ratioRed = rules.includes('text-ratio') && ratioReport(groups, capPct);
  const languages = rels.map(languageOf);
  const label = filesLabel(languages);
  err(message('conventions.summary', { count: found.length, files: rels.length, label }));
  const status = found.length > 0 || ratioRed ? 1 : 0;
  out(status === 0 ? message('conventions.clear', { label }) : message('conventions.red', { waivers: waiverExamples(languages) }));
  return status;
}

export interface GateOptions {
  repoRoot: string;
  pr: string | null;
  repo: string | null;
  base: string | null;
  files: string[];
  excludes: string[];
  capPct: number | null;
}

/** The gate end to end: resolve the changed files, collect their facts, print the report and verdict. */
export function checkConventions(options: GateOptions): number {
  const { repoRoot, files } = options;
  let config;
  let rels: string[];
  try {
    config = loadConfig(repoRoot);
    rels = files.length > 0 ? files : changedSourceFiles(resolveBaseRef(options.pr, options.repo, options.base, repoRoot), repoRoot);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    err(message('conventions.error', { error: error.message }));
    return 2;
  }
  rels = select(rels, files.length > 0, [...config.conventions.exempt, ...options.excludes]);
  let facts: Map<string, Facts>;
  try {
    facts = collect(rels, repoRoot, repoRoot);
  } catch (error) {
    if (!(error instanceof FactsError)) throw error;
    if (error.message) err(message('conventions.error', { error: error.message }));
    return 2;
  }
  return report(rels, facts, options.capPct ?? config.conventions.text_ratio_max * 100, config.conventions.rules);
}
