// The format of a committed config file: its `format` key, the check every gated command runs, the stamp.
import {
  YAMLError,
  byCodePoint,
  canonicalRepr,
  configFormats,
  loadYaml,
  message,
  normalize,
} from '../contract/index.js';
import { ConfigError } from './error.js';
import { configSource, ownFile } from './files.js';
import { basename } from 'node:path';
import { parseConfig, readConfigText } from './read.js';

export const FORMAT_KEY = 'format';
const VERSION_RE = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;
const BLANK = ' \t\r';
// A top-level `format` line with one single-line scalar value: its value, then its trailing whitespace and comment.
const FORMAT_LINE = new RegExp(
  String.raw`^${FORMAT_KEY}:[ \t]+` +
    String.raw`(?<value>'(?:[^']|'')*'|"(?:[^"\\]|\\.)*"|[^\s#'"|>{}\[\],&*!%@` + '`' + String.raw`](?:[^#]|(?<![ \t])#)*?)` +
    String.raw`(?<rest>[ \t]*(?:#.*)?)$`,
);

/** The committed config file: its exact text and its top-level mapping, null for an empty document. */
export interface Committed {
  text: string;
  data: Map<unknown, unknown> | null;
}

/** Every released format of config file `file`, oldest first. */
export function releasedFormats(file: string): string[] {
  return configFormats(file);
}

/** The format of config file `file` its package reads and writes: the last released one. */
export function currentFormat(file: string): string {
  return configFormats(file).at(-1) as string;
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

/** Committed config file `file`, null without it; ConfigError when it is unreadable, not YAML or not a mapping. */
export function readCommitted(root: string, file: string): Committed | null {
  const text = readConfigText(root, file);
  if (text === null) return null;
  const data = parseConfig(text, file);
  if (data !== null && !(data instanceof Map)) throw new ConfigError(`${file}: top level must be a mapping`);
  return { text, data };
}

/** The refusal of config file `file`'s `format`, or null when it declares `current` (default: its current format). */
export function formatProblem(
  data: Map<unknown, unknown>,
  file: string,
  current: string = currentFormat(basename(file)),
): string | null {
  const kind = basename(file) === ownFile() ? 'format.trmv-' : 'format.';
  if (!data.has(FORMAT_KEY)) return message(`${kind}missing`, { current });
  const declared = data.get(FORMAT_KEY);
  if (!isVersion(declared)) return message(`${kind}invalid`, { value: declared, current });
  const sign = compareVersions(declared, current);
  if (sign === 0) return null;
  return message(sign > 0 ? `${kind}newer` : `${kind}older`, { declared, current });
}

/**
 * The format check's refusal for the config file `pkg` reads, or null to go on (also without one, with several, or for a
 * file it cannot judge).
 */
export function checkFormat(root: string, pkg = 'trmv'): string | null {
  let name: string | null;
  let committed: Committed | null;
  try {
    name = configSource(root, pkg);
    committed = name === null ? null : readCommitted(root, name);
  } catch (error) {
    if (error instanceof ConfigError) return null;
    throw error;
  }
  return name !== null && committed?.data ? formatProblem(committed.data, name) : null;
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

/** `text` declaring `current`: a `format` line inserted or its value replaced, verified to change only that key; null when it cannot be. */
export function stampFormat(text: string, current: string): string | null {
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
