// The repo format: `format` in the committed `living-architecture.yaml`, the check every gated command runs, the stamp.
import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  YAMLError,
  byCodePoint,
  canonicalRepr,
  configFile,
  configFormat,
  decodeUtf8,
  loadYaml,
  message,
  normalize,
} from '../contract/index.js';
import { ConfigError } from './error.js';

export const FORMAT_KEY = 'format';
const VERSION_RE = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const BLANK = ' \t\r';

/** The committed config file: its exact text and its top-level mapping, null for an empty document. */
export interface Committed {
  text: string;
  data: Map<unknown, unknown> | null;
}

/** The repo format this la reads and writes. */
export function currentFormat(): string {
  return configFormat();
}

/** Three dot-separated decimal integers without leading zeros. */
export function isVersion(value: unknown): value is string {
  return typeof value === 'string' && VERSION_RE.test(value);
}

/** The sign of `a - b`, component by component as integers of any size (by digit count, then digits). */
export function compareVersions(a: string, b: string): number {
  const ys = b.split('.');
  for (const [i, x] of a.split('.').entries()) {
    const y = ys[i] ?? '';
    if (x.length !== y.length) return x.length > y.length ? 1 : -1;
    if (x !== y) return x > y ? 1 : -1;
  }
  return 0;
}

const isFile = (path: string): boolean => {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
};

/** The committed file, null without one; ConfigError when it is unreadable, not YAML or not a mapping. */
export function readCommitted(root: string): Committed | null {
  const path = join(root, configFile());
  if (!isFile(path)) return null;
  let text: string;
  let data: unknown;
  try {
    text = decodeUtf8(readFileSync(path));
    data = loadYaml(text);
  } catch (error) {
    if (error instanceof YAMLError || error instanceof TypeError || (error as NodeJS.ErrnoException).code !== undefined) {
      throw new ConfigError(`${configFile()}: ${(error as Error).message}`);
    }
    throw error;
  }
  if (data !== null && !(data instanceof Map)) throw new ConfigError(`${configFile()}: top level must be a mapping`);
  return { text, data };
}

/** The refusal of a committed mapping's `format`, or null when it declares the current format. */
export function formatProblem(data: Map<unknown, unknown>): string | null {
  const current = currentFormat();
  if (!data.has(FORMAT_KEY)) return message('format.missing', { current });
  const declared = data.get(FORMAT_KEY);
  if (!isVersion(declared)) return message('format.invalid', { value: declared, current });
  const sign = compareVersions(declared, current);
  if (sign === 0) return null;
  return message(sign > 0 ? 'format.newer' : 'format.older', { declared, current });
}

/** The format check's refusal, or null to go on (also for a committed file it cannot judge). */
export function checkFormat(root: string): string | null {
  let committed: Committed | null;
  try {
    committed = readCommitted(root);
  } catch (error) {
    if (error instanceof ConfigError) return null;
    throw error;
  }
  return committed?.data ? formatProblem(committed.data) : null;
}

/** The canonical repr of a normalized value, with every mapping's entries sorted. */
function unorderedRepr(value: unknown): string {
  if (value instanceof Map) {
    const entries = [...value].map(([k, v]) => `${unorderedRepr(k)}: ${unorderedRepr(v)}`);
    return `{${entries.toSorted(byCodePoint).join(', ')}}`;
  }
  if (Array.isArray(value)) return `[${value.map(unorderedRepr).join(', ')}]`;
  return canonicalRepr(value);
}

function stripStart(text: string, chars: string): string {
  let start = 0;
  while (start < text.length && chars.includes(text.charAt(start))) start += 1;
  return text.slice(start);
}

function stripEnd(text: string, chars: string): string {
  let end = text.length;
  while (end > 0 && chars.includes(text.charAt(end - 1))) end -= 1;
  return text.slice(0, end);
}

/** The index of the first line after the leading comments, blank lines, directives and a `---` marker. */
function insertAt(lines: string[]): number {
  for (const [index, line] of lines.entries()) {
    const content = stripEnd(line, '\r\n');
    if (stripEnd(content, BLANK) === '---') return index + 1;
    const stripped = stripStart(content, BLANK);
    if (stripped && !stripped.startsWith('#') && !content.startsWith('%')) return index;
  }
  return lines.length;
}

function parsed(text: string): { value: unknown } | null {
  try {
    return { value: loadYaml(text) };
  } catch (error) {
    if (error instanceof YAMLError) return null;
    throw error;
  }
}

/** `text` with a `format: <current>` line inserted, verified to add only that key; null when it cannot be. */
export function stampFormat(text: string): string | null {
  const before = parsed(text);
  if (before === null || (before.value !== null && !(before.value instanceof Map))) return null;
  const original = (before.value as Map<unknown, unknown> | null) ?? new Map<unknown, unknown>();
  const firstBreak = text.indexOf('\n');
  const newline = firstBreak > 0 && text[firstBreak - 1] === '\r' ? '\r\n' : '\n';
  const lines = text.split('\n').map((line) => `${line}\n`);
  lines[lines.length - 1] = (lines.at(-1) ?? '').slice(0, -1);
  if (lines.at(-1) === '') lines.pop();
  const index = insertAt(lines);
  if (index === lines.length && lines.length > 0 && !(lines.at(-1) ?? '').endsWith('\n')) lines[lines.length - 1] += newline;
  lines.splice(index, 0, `${FORMAT_KEY}: ${currentFormat()}${newline}`);
  const stamped = lines.join('');
  const after = parsed(stamped);
  if (after === null || original.has(FORMAT_KEY)) return null;
  const expected = new Map([...original, [FORMAT_KEY, currentFormat()]]);
  return unorderedRepr(normalize(after.value)) === unorderedRepr(normalize(expected)) ? stamped : null;
}
