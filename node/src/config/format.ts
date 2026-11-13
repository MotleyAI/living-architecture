// The repo format: `format` in the committed `living-architecture.yaml`, the check every gated command runs, the stamp.
import { readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  YAMLError,
  byCodePoint,
  canonicalRepr,
  configFile,
  configFormats,
  decodeUtf8,
  loadYaml,
  message,
  normalize,
} from '../contract/index.js';
import { ConfigError } from './error.js';

export const FORMAT_KEY = 'format';
const VERSION_RE = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const BLANK = ' \t\r';
// A top-level `format` line with one single-line scalar value: its value, then its trailing whitespace and comment.
const FORMAT_LINE = new RegExp(
  `^${FORMAT_KEY}:[ \\t]+` +
    String.raw`(?<value>'(?:[^']|'')*'|"(?:[^"\\]|\\.)*"|[^\s#'"|>{}\[\],&*!%@` + '`' + String.raw`](?:[^#]|(?<![ \t])#)*?)` +
    String.raw`(?<rest>[ \t]*(?:#.*)?)$`,
);

/** The committed config file: its exact text and its top-level mapping, null for an empty document. */
export interface Committed {
  text: string;
  data: Map<unknown, unknown> | null;
}

/** Every released repo format, oldest first. */
export function releasedFormats(): string[] {
  return configFormats();
}

/** The repo format this la reads and writes: the last released one. */
export function currentFormat(): string {
  return configFormats().at(-1) as string;
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

/** The refusal of a committed mapping's `format`, or null when it declares `current` (default: the current format). */
export function formatProblem(data: Map<unknown, unknown>, current: string = currentFormat()): string | null {
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

/** `text` split after each line break; no empty last line. */
function linesOf(text: string): string[] {
  const lines = text.split('\n').map((line) => `${line}\n`);
  lines[lines.length - 1] = (lines.at(-1) ?? '').slice(0, -1);
  if (lines.at(-1) === '') lines.pop();
  return lines;
}

/** `text` with a `format: <current>` line after its leading comments, directives and document marker. */
function inserted(text: string, current: string): string {
  const firstBreak = text.indexOf('\n');
  const newline = firstBreak > 0 && text[firstBreak - 1] === '\r' ? '\r\n' : '\n';
  const lines = linesOf(text);
  const index = insertAt(lines);
  if (index === lines.length && lines.length > 0 && !(lines.at(-1) ?? '').endsWith('\n')) lines[lines.length - 1] += newline;
  lines.splice(index, 0, `${FORMAT_KEY}: ${current}${newline}`);
  return lines.join('');
}

/** `text` with the value on its one top-level `format` line replaced by `current`; null without exactly one. */
function replaced(text: string, current: string): string | null {
  const lines = linesOf(text);
  const found = [...lines.keys()].filter((i) => (lines[i] ?? '').startsWith(`${FORMAT_KEY}:`));
  const at = found[0];
  if (found.length !== 1 || at === undefined) return null;
  const line = lines[at] ?? '';
  const content = stripEnd(line, '\r\n');
  const match = FORMAT_LINE.exec(content);
  if (match === null) return null;
  const valueAt = content.length - (match.groups?.value ?? '').length - (match.groups?.rest ?? '').length;
  lines[at] = content.slice(0, valueAt) + current + (match.groups?.rest ?? '') + line.slice(content.length);
  return lines.join('');
}

/**
 * `text` declaring `current` (default: the current format): a `format` line inserted or its value replaced,
 * verified to change only that key; null when it cannot be.
 */
export function stampFormat(text: string, current: string = currentFormat()): string | null {
  const before = parsed(text);
  if (before === null || (before.value !== null && !(before.value instanceof Map))) return null;
  const original = (before.value as Map<unknown, unknown> | null) ?? new Map<unknown, unknown>();
  const stamped = original.has(FORMAT_KEY) ? replaced(text, current) : inserted(text, current);
  if (stamped === null) return null;
  const after = parsed(stamped);
  if (after === null) return null;
  const expected = new Map([...original, [FORMAT_KEY, current]]);
  return unorderedRepr(normalize(after.value)) === unorderedRepr(normalize(expected)) ? stamped : null;
}
