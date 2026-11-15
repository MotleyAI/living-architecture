// `.tsc-baseline.json` kept aligned with a refactor: each baselined diagnostic followed to its key after the edits.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type * as TS from 'typescript';
import { ConfigError, findRepoRoot, loadConfig } from '../config/index.js';
import { byCodePoint, language, message } from '../contract/index.js';
import { baselineKey, canonical, parseBaseline, parseTscOutput, posix, posixRel, renderBaseline, ts } from '../lang/index.js';
import { splitBom } from './edits.js';
import { mapPosition, type PositionMap } from './position.js';
import type { Refactor } from './session.js';
import { Workspace } from './workspace.js';
import type { Write } from './writer.js';

/** One diagnostic: its baseline key, code and start. */
interface Instance {
  key: string;
  code: string;
  start: number;
}

/** The pre-emit errors of `file` in `services`' programs, keyed as `la-typecheck` keys tsc's output. */
function diagnostics(services: TS.LanguageService[], file: string, repoRoot: string): Instance[] {
  const host: TS.FormatDiagnosticsHost = { getCurrentDirectory: () => repoRoot, getCanonicalFileName: (name) => name, getNewLine: () => '\n' };
  const seen = new Set<string>();
  const out: Instance[] = [];
  for (const service of services) {
    const program = service.getProgram();
    const source = program?.getSourceFile(file);
    if (program === undefined || source === undefined) continue;
    for (const d of ts().getPreEmitDiagnostics(program, source)) {
      if (d.file !== source || d.category !== ts().DiagnosticCategory.Error) continue;
      const parsed = parseTscOutput(ts().formatDiagnostic(d, host)).diagnostics[0];
      if (parsed === undefined) continue;
      const key = baselineKey(posixRel(repoRoot, parsed.file), parsed.code, parsed.message);
      const id = `${d.start ?? 0}\0${key}`;
      if (seen.has(id)) continue;
      seen.add(id);
      out.push({ key, code: parsed.code, start: d.start ?? 0 });
    }
  }
  return out;
}

/** The baseline's path and multiset when the repo checks TypeScript against one, else null. */
function configured(repoRoot: string): { path: string; name: string } | null {
  let command: string | null;
  try {
    command = loadConfig(repoRoot).commands.typecheck.typescript;
  } catch (error) {
    if (error instanceof ConfigError) return null;
    throw error;
  }
  const name: string = language('typescript').baseline_file;
  const path = join(repoRoot, name);
  return command === null || !existsSync(path) ? null : { path, name };
}

/** Where each of key `key`'s instances lands after the refactor; null for one that cannot be followed. */
type Follow = (file: string, instance: Instance) => string | null;

/** The baseline with each key's count moved to the keys its instances land on, and the keys left where they are. */
function moved(counts: Map<string, number>, before: Map<string, Instance[]>, follow: Follow): { counts: Map<string, number>; stuck: string[] } {
  const out = new Map(counts);
  const stuck: string[] = [];
  const shift = (from: string, to: string, count: number): void => {
    if (from === to || count === 0) return;
    out.set(to, (out.get(to) ?? 0) + count);
    if ((out.get(from) ?? 0) === count) out.delete(from);
    else out.set(from, (out.get(from) ?? 0) - count);
  };
  for (const [key, count] of counts) {
    const [file] = JSON.parse(key) as [string, string, string];
    const instances = (before.get(file) ?? []).filter((i) => i.key === key);
    const targets = instances.map((i) => follow(file, i));
    const distinct = new Set(targets);
    if (instances.length === 0 || (distinct.size === 1 && distinct.has(key))) continue;
    if (targets.includes(null) || (distinct.size > 1 && count < instances.length)) stuck.push(key);
    else if (distinct.size === 1) shift(key, targets[0] as string, count);
    else for (const target of targets) shift(key, target as string, 1);
  }
  return { counts: out, stuck };
}

/** The realigned baseline to write with the refactor's files (null when it does not change), and its warnings. */
export function alignBaseline(r: Refactor, map: PositionMap, texts: Map<string, string>): { write: Write | null; warnings: string[] } {
  const none = { write: null, warnings: [] };
  const repoRoot = findRepoRoot(r.root);
  const baseline = configured(repoRoot);
  const old = baseline === null ? null : readFileSync(baseline.path, 'utf8');
  const counts = old === null ? null : parseBaseline(old);
  if (baseline === null || old === null || counts === null || counts.size === 0) return none;
  if (map.edits.size === 0 && map.moves.size === 0) return none;
  const listed = [...new Set([...counts.keys()].map((key) => (JSON.parse(key) as [string])[0]))];
  const before = new Map<string, Instance[]>();
  for (const file of listed) {
    const path = join(repoRoot, file);
    if (existsSync(path) && r.workspace.owner(path) !== null) before.set(file, diagnostics(r.services(path), path, repoRoot));
  }
  const olds = new Map([...map.moves].map(([from, to]) => [to, from]));
  const overlay = (path: string): string | null | undefined => {
    if (map.moves.has(path)) return null;
    const old = olds.get(path) ?? path;
    return texts.get(old) ?? (olds.has(path) ? splitBom(readFileSync(old, 'utf8'))[1] : undefined);
  };
  const after = new Workspace(r.root, overlay, new Map([...map.moves].map(([from, to]) => [canonical(from), to])));
  const cache = new Map<string, Instance[]>();
  const afterOf = (path: string): Instance[] => {
    let found = cache.get(path);
    if (found === undefined) {
      found = diagnostics(after.holding(olds.get(path) ?? path, path), path, repoRoot);
      cache.set(path, found);
    }
    return found;
  };
  const follow: Follow = (file, instance) => {
    const landed = mapPosition(map, join(repoRoot, file), instance.start);
    if (landed === null) return null;
    return afterOf(landed.file).find((i) => i.code === instance.code && i.start === landed.position)?.key ?? null;
  };
  const result = moved(counts, before, follow);
  const warnings = result.stuck
    .map((key) => JSON.parse(key) as [string, string, string])
    .sort((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]) || byCodePoint(a[2], b[2]))
    .map(([path, code]) => message('refactor.baseline-ambiguous', { baseline: posix(baseline.name), code, path }));
  const text = renderBaseline(result.counts);
  const same = result.counts.size === counts.size && [...counts].every(([key, count]) => result.counts.get(key) === count);
  return { write: same || text === old ? null : { path: baseline.path, old, text }, warnings: [...new Set(warnings)] };
}
