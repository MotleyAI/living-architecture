// `la-leak-check`: the tokens that show la or trmv was used, in a stealth branch or in a text.
import { spawnSync } from 'node:child_process';
// eslint-disable-next-line no-restricted-imports -- stdin only
import { readFileSync } from 'node:fs';
import { mergeBase, resolveBaseRef } from 'type-rename-move/changes';
import { ConfigError } from 'type-rename-move/config';
import { byCodePoint, isWordStart, manifest as trmvManifest, stealthRegistry as trmvRegistry } from 'type-rename-move/contract';
import { loadRaw, resolveRaw, tracksOpenspec } from '../config/index.js';
import { leakTokenGroups, manifest, message, stealthRegistry } from '../contract/index.js';

const asciiLower = (text: string): string => text.replace(/[A-Z]/g, (c) => c.toLowerCase());

/** The code point that ends just before `index`. */
function before(text: string, index: number): string {
  const low = text.charCodeAt(index - 1);
  return low >= 0xdc00 && low <= 0xdfff && index >= 2 ? text.slice(index - 2, index) : text.slice(index - 1, index);
}

/** The code point that starts at `index`. */
const after = (text: string, index: number): string => String.fromCodePoint(text.codePointAt(index) ?? 0);

/** Where `token` (lowercase) first occurs in `text` (ASCII-lowercased) with no word character touching it. */
function firstMatch(text: string, token: string): number | null {
  for (let start = text.indexOf(token); start >= 0; start = text.indexOf(token, start + 1)) {
    const end = start + token.length;
    const touchedBefore = start > 0 && isWordStart(token[0] ?? '') && isWordStart(before(text, start));
    const touchedAfter = end < text.length && isWordStart(token.at(-1) ?? '') && isWordStart(after(text, end));
    if (!touchedBefore && !touchedAfter) return start;
  }
  return null;
}

/** The tokens `text` holds, case-insensitively, each once, by first position and then longer first. */
export function findTokens(text: string, tokens: string[]): string[] {
  const lowered = asciiLower(text);
  const found: [number, number, string][] = [];
  for (const token of new Set(tokens)) {
    const start = firstMatch(lowered, asciiLower(token));
    if (start !== null) found.push([start, -[...token].length, token]);
  }
  return found.toSorted((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , token]) => token);
}

/** The core tokens, every command name and registry path, and the waivable tokens not in `allow` (OpenSpec only when the
 * repo tracks nothing under openspec/). */
export function leakTokens(repoRoot: string, allow: string[]): string[] {
  const [core, waivable] = leakTokenGroups();
  const commands = [...Object.keys(manifest()), ...Object.keys(trmvManifest())];
  const registry = [...stealthRegistry()[0], ...trmvRegistry()];
  const dropped = new Set([...allow, ...(tracksOpenspec(repoRoot) ? ['OpenSpec'] : [])]);
  return [...new Set([...core, ...commands, ...registry, ...waivable.filter((t) => !dropped.has(t))])];
}

function git(root: string, ...args: string[]): Buffer {
  const proc = spawnSync('git', args, { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  if (proc.status !== 0) throw new ConfigError(message('changes.git-failed', { args: args.join(' ') }));
  return proc.stdout;
}

const text = (data: Buffer): string => new TextDecoder('utf-8').decode(data);

function branch(root: string): string | null {
  const proc = spawnSync('git', ['symbolic-ref', '--quiet', '--short', 'HEAD'], { cwd: root }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  const name = text(proc.stdout ?? Buffer.alloc(0)).trim();
  return proc.status === 0 && name ? name : null;
}

/** Each commit since `base`, oldest first, with its full message. */
function commits(root: string, base: string): [string, string][] {
  const records = text(git(root, 'log', '--reverse', '-z', '--format=%H%n%B', `${base}..HEAD`)).split('\0').filter((r) => r);
  return records.map((r) => {
    const cut = r.indexOf('\n');
    return cut === -1 ? [r, ''] : [r.slice(0, cut), r.slice(cut + 1)];
  });
}

/** Each path changed between `base` and HEAD but deleted: its status letter, old path and new path. */
function entries(root: string, base: string): [string, string, string][] {
  const fields = text(git(root, 'diff', '-z', '--name-status', '-M', base, 'HEAD', '--')).split('\0');
  const out: [string, string, string][] = [];
  for (let i = 0; i < fields.length && fields[i]; ) {
    const status = (fields[i] ?? '')[0] ?? '';
    if ('RC'.includes(status)) {
      out.push([status, fields[i + 1] ?? '', fields[i + 2] ?? '']);
      i += 3;
    } else {
      out.push([status, fields[i + 1] ?? '', fields[i + 1] ?? '']);
      i += 2;
    }
  }
  return out.filter(([status]) => status !== 'D');
}

/** The lines the diff of one path adds, with their line numbers in the new file. */
function addedLines(root: string, base: string, old: string, now: string): [number, string][] {
  const patch = text(git(root, 'diff', '-U0', '--no-color', '--no-ext-diff', '-M', base, 'HEAD', '--', old, now));
  const out: [number, string][] = [];
  let number: number | null = null;
  for (const raw of patch.split('\n')) {
    if (raw.startsWith('@@ ')) number = Number((raw.split(' ')[2] ?? '').slice(1).split(',')[0]);
    else if (number !== null && raw.startsWith('+')) out.push([number++, raw.slice(1)]);
  }
  return out;
}

/** The hits of the branch name, the commit messages and the added paths and lines since the merge base. */
export function scanBranch(root: string, baseRef: string, tokens: string[]): string[] {
  const base = mergeBase(baseRef, root);
  const hits: string[] = [];
  const name = branch(root);
  if (name !== null) hits.push(...findTokens(name, tokens).map((token) => message('leaks.branch', { token })));
  for (const [commit, body] of commits(root, base)) {
    hits.push(...findTokens(body, tokens).map((token) => message('leaks.commit', { commit: commit.slice(0, 7), token })));
  }
  for (const [status, old, now] of entries(root, base).toSorted((a, b) => byCodePoint(a[2], b[2]))) {
    if ('ARC'.includes(status)) hits.push(...findTokens(now, tokens).map((token) => message('leaks.path', { path: now, token })));
    for (const [line, added] of addedLines(root, base, old, now)) {
      hits.push(...findTokens(added, tokens).map((token) => message('leaks.line', { path: now, line, token })));
    }
  }
  return hits;
}

/** The hits of each line of `input`. */
export function scanText(input: string, tokens: string[]): string[] {
  const lines = input.split('\n');
  if (lines.at(-1) === '') lines.pop();
  return lines.flatMap((line, i) => findTokens(line, tokens).map((token) => message('leaks.stdin', { line: i + 1, token })));
}

/** `la-leak-check`: print each hit; exit 1 with hits, 0 without or outside stealth mode, 2 on an error. */
export function run(root: string, base: string | null): number {
  let hits: string[];
  try {
    const raw = loadRaw(root);
    if (!raw.source?.stealth) {
      process.stderr.write(`${message('leaks.not-stealth')}\n`);
      return 0;
    }
    const config = resolveRaw(root, raw);
    const tokens = leakTokens(root, config.leaks.allow);
    hits = base === null ? scanText(text(readFileSync(0)), tokens) : scanBranch(root, resolveBaseRef(base, root), tokens);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('leaks.error', { error: error.message })}\n`);
    return 2;
  }
  for (const hit of hits) process.stdout.write(`${hit}\n`);
  return hits.length > 0 ? 1 : 0;
}
