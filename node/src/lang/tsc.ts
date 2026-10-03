// tsc as la-typecheck's TypeScript checker: its `--pretty false` diagnostics and the multiset baseline ratchet.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { isAbsolute, join, relative, sep } from 'node:path';
import { byCodePoint, message } from '../contract/index.js';

export interface TscDiagnostic {
  file: string;
  line: number;
  col: number;
  code: string;
  message: string;
}

const DIAGNOSTIC_RE = /^(.+)\((\d+),(\d+)\): error (TS\d+): (.*)$/;
const GLOBAL_RE = /^error TS\d+: /;

/** Diagnostics with their indented continuation lines, and the lines of diagnostics without a file. */
export function parseTscOutput(text: string): { diagnostics: TscDiagnostic[]; globals: string[] } {
  const diagnostics: TscDiagnostic[] = [];
  const globals: string[] = [];
  let current: TscDiagnostic | null = null;
  for (const line of text.split(/\r?\n/)) {
    const m = DIAGNOSTIC_RE.exec(line);
    if (m !== null) {
      current = { file: m[1] ?? '', line: Number(m[2]), col: Number(m[3]), code: m[4] ?? '', message: m[5] ?? '' };
      diagnostics.push(current);
    } else if (current !== null && /^\s+\S/.test(line)) {
      current.message += `\n${line}`;
    } else {
      current = null;
      if (GLOBAL_RE.test(line)) globals.push(line);
    }
  }
  return { diagnostics, globals };
}

type Counts = Map<string, number>;

const keyOf = (file: string, code: string, msg: string): string => JSON.stringify([file, code, msg]);

const posixRel = (root: string, file: string): string => (isAbsolute(file) ? relative(root, file) : file).split(sep).join('/');

/** The baseline JSON: keys sorted by file, code and message, 2-space indented, trailing newline. */
function render(counts: Counts): string {
  const keys = [...counts.keys()].map((k) => JSON.parse(k) as [string, string, string]);
  keys.sort((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]) || byCodePoint(a[2], b[2]));
  const files: Record<string, { code: string; message: string; count: number }[]> = {};
  for (const [file, code, msg] of keys) (files[file] ??= []).push({ code, message: msg, count: counts.get(keyOf(file, code, msg)) ?? 0 });
  return `${JSON.stringify({ files }, null, 2)}\n`;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

function validEntry(entry: unknown): entry is { code: string; message: string; count: number } {
  if (!isObject(entry) || Object.keys(entry).sort().join() !== 'code,count,message') return false;
  const { code, message: msg, count } = entry;
  return typeof code === 'string' && typeof msg === 'string' && Number.isInteger(count) && (count as number) > 0;
}

/** The baseline multiset; empty when the file is absent, null when it is malformed. */
function load(path: string): Counts | null {
  if (!existsSync(path)) return new Map();
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return null;
  }
  if (!isObject(data) || Object.keys(data).join() !== 'files' || !isObject(data.files)) return null;
  const counts: Counts = new Map();
  for (const [file, entries] of Object.entries(data.files)) {
    if (!Array.isArray(entries) || !entries.every(validEntry)) return null;
    for (const e of entries) counts.set(keyOf(file, e.code, e.message), (counts.get(keyOf(file, e.code, e.message)) ?? 0) + e.count);
  }
  return counts;
}

export interface TscRun {
  repoRoot: string;
  /** The resolved command words; `--pretty false` is appended. */
  argv: string[];
  /** The configured command, for messages. */
  command: string;
  baseline: string;
  write: boolean;
}

/** Run tsc and ratchet its diagnostics against the baseline; the la-typecheck exit code. */
export function checkTypescript({ repoRoot, argv, command, baseline, write }: TscRun): number {
  const [cmd = '', ...args] = argv;
  const proc = spawnSync(cmd, [...args, '--pretty', 'false'], { cwd: repoRoot, maxBuffer: 1 << 30 });
  const stdout = proc.stdout?.toString('utf8') ?? '';
  const stderr = proc.stderr?.toString('utf8') ?? '';
  const fail = (text: string): number => {
    process.stdout.write(stdout);
    process.stderr.write(stderr);
    process.stderr.write(`${text}\n`);
    return 2;
  };
  const parsed = [parseTscOutput(stdout), parseTscOutput(stderr)];
  const diagnostics = parsed.flatMap((p) => p.diagnostics).map((d) => ({ ...d, file: posixRel(repoRoot, d.file) }));
  if (parsed.some((p) => p.globals.length > 0)) return fail(message('typecheck.global-diagnostic', { language: 'typescript' }));
  if (proc.status !== 0 && diagnostics.length === 0) {
    return fail(message('typecheck.checker-failed', { language: 'typescript', command, code: proc.status ?? proc.signal ?? '' }));
  }
  const now: Counts = new Map();
  for (const d of diagnostics) now.set(keyOf(d.file, d.code, d.message), (now.get(keyOf(d.file, d.code, d.message)) ?? 0) + 1);
  const path = join(repoRoot, baseline);
  if (write) {
    writeFileSync(path, render(now));
    process.stderr.write(`${message('typecheck.write', { language: 'typescript', baseline })}\n`);
    return 0;
  }
  const base = load(path);
  if (base === null) return fail(message('typecheck.baseline-invalid', { language: 'typescript', baseline }));
  let added = 0;
  for (const [key, count] of now) added += Math.max(0, count - (base.get(key) ?? 0));
  if (added > 0) {
    for (const d of diagnostics) {
      const key = keyOf(d.file, d.code, d.message);
      const [was, is] = [base.get(key) ?? 0, now.get(key) ?? 0];
      if (is <= was) continue;
      const values = { ...d, baseline: was, now: is };
      process.stdout.write(`${message(was === 0 ? 'typecheck.new-error' : 'typecheck.count', values)}\n`);
    }
    process.stderr.write(`${message('typecheck.new-errors', { language: 'typescript', count: added, baseline })}\n`);
    return 1;
  }
  let fixed = 0;
  for (const [key, count] of base) fixed += count - (now.get(key) ?? 0);
  if (fixed > 0) {
    writeFileSync(path, render(now));
    process.stderr.write(`${message('typecheck.shrink', { language: 'typescript', count: fixed, baseline })}\n`);
  }
  return 0;
}
