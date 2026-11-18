// The 0.4.0 step of `la-arch-migrate`: `conventions.exempt` moves, as text, to a top-level `exempt` key.
import { isDeepStrictEqual } from 'node:util';
import { YAMLError, loadYaml, message, normalize } from 'deterministic-refactor/contract';

const KEY_LINE = /^conventions:[ \t]*(?:#.*)?$/;
const EXEMPT_LINE = /^exempt:(?:[ \t]|$)/;
const FORMAT_LINE = /^format:[ \t]/;
const MERGE_KEY = /^(?:<<|!!merge|!<tag:yaml\.org,2002:merge>)[ \t]*:/;
// `&`, `*` or `!` where a node starts: an anchor, an alias or a tag.
const NODE_PROPERTY = /(?:^[ \t]*|[[{,][ \t]*|(?:^|[ \t])[-?][ \t]+|:[ \t]+)[&*!]/m;
const SEQUENCE_ITEM = /^-(?:[ \t]|$)/;

/** `conventions.exempt` cannot be moved faithfully. */
export class ExemptNotMigratable extends Error {
  constructor() {
    super(message('arch-migrate.exempt-by-hand'));
  }
}

/** `text` with quoted scalars blanked and comments removed, line breaks kept. */
function masked(text: string): string {
  const out: string[] = [];
  let quote: string | null = null;
  let i = 0;
  while (i < text.length) {
    const char = text[i] as string;
    if (quote !== null) {
      if (char === '\\' && quote === '"' && i + 1 < text.length) {
        const next = text[i + 1] as string;
        out.push('\r\n'.includes(next) ? `x${next}` : 'xx');
        i += 2;
        continue;
      }
      if (char === quote && quote === "'" && text[i + 1] === "'") {
        out.push('xx');
        i += 2;
        continue;
      }
      if (char === quote) quote = null;
      out.push(char === '\r' || char === '\n' ? char : 'x');
    } else if (char === "'" || char === '"') {
      quote = char;
      out.push('x');
    } else if (char === '#' && (i === 0 || ' \t\r\n'.includes(text[i - 1] as string))) {
      while (i < text.length && text[i] !== '\r' && text[i] !== '\n') i += 1;
      continue;
    } else out.push(char);
    i += 1;
  }
  return out.join('');
}

const indentOf = (line: string): number => line.length - line.replace(/^ +/, '').length;
const blank = (line: string): boolean => line.trim() === '';
const comment = (line: string): boolean => line.trim().startsWith('#');
const bare = (line: string): string => line.replace(/[\r\n]+$/, '');
const dedent = (line: string, by: number): string => line.slice(Math.min(by, indentOf(line)));
const belongs = (line: string): boolean => blank(line) || comment(line) || indentOf(line) > 0;

/** `text` split after each line break, every break kept (Python's `splitlines(keepends=True)` for \n, \r, \r\n). */
function linesOf(text: string): string[] {
  return text.match(/[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$/g) ?? [];
}

/** The leading run of `body` that still belongs to the `conventions` mapping. */
function bodyEnd(body: string[]): number {
  let end = 0;
  while (end < body.length && belongs(body[end] as string)) end += 1;
  return end;
}

/** The conventions body's child indent and the `exempt` entry's line span; ExemptNotMigratable if absent. */
function entrySpan(lines: string[], key: number): [indent: number, start: number, stop: number] {
  const end = key + 1 + bodyEnd(lines.slice(key + 1));
  const children: number[] = [];
  for (let i = key + 1; i < end; i += 1) if (!blank(lines[i] as string) && !comment(lines[i] as string)) children.push(i);
  if (children.length === 0) throw new ExemptNotMigratable();
  const indent = indentOf(lines[children[0] as number] as string);
  const atIndent = children.filter((i) => indentOf(lines[i] as string) === indent);
  if (atIndent.some((i) => MERGE_KEY.test(masked(lines[i] as string).trim()))) throw new ExemptNotMigratable();
  const starts = atIndent.filter((i) => EXEMPT_LINE.test(bare(lines[i] as string).slice(indent)));
  if (starts.length !== 1) throw new ExemptNotMigratable();
  const start = starts[0] as number;
  const inline = (lines[start] as string).slice(indent + 'exempt:'.length).trim();
  let stop = start + 1;
  while (stop < end) {
    const line = lines[stop] as string;
    const sequenceItem = !inline && indentOf(line) === indent && SEQUENCE_ITEM.test(bare(line).slice(indent));
    if (!(blank(line) || indentOf(line) > indent || sequenceItem)) break;
    stop += 1;
  }
  while (blank(lines[stop - 1] as string)) stop -= 1;
  return [indent, start, stop];
}

function expected(data: Map<unknown, unknown>, current: string): Map<unknown, unknown> {
  const conventions = data.get('conventions') as Map<unknown, unknown>;
  const kept = new Map([...conventions].filter(([k]) => k !== 'exempt'));
  const out = new Map(data);
  out.set('format', current);
  out.set('exempt', conventions.get('exempt'));
  if (kept.size > 0) out.set('conventions', kept);
  else out.delete('conventions');
  return out;
}

/** `text`, stamped at `current`, with `conventions.exempt` moved to directly after the `format` line. */
export function moveExempt(text: string, current: string): string {
  let data: unknown;
  try {
    data = loadYaml(text);
  } catch (error) {
    if (error instanceof YAMLError) return text;
    throw error;
  }
  const conventions = data instanceof Map ? data.get('conventions') : undefined;
  if (!(data instanceof Map) || !(conventions instanceof Map) || !conventions.has('exempt')) return text;
  if (data.has('exempt')) throw new ExemptNotMigratable();
  const lines = linesOf(text);
  const keys = lines.flatMap((line, i) => (line.startsWith('conventions:') ? [i] : []));
  if (keys.length !== 1 || !KEY_LINE.test(bare(lines[keys[0] as number] as string))) {
    throw new ExemptNotMigratable();
  }
  const key = keys[0] as number;
  const [indent, start, stop] = entrySpan(lines, key);
  const entry = lines.slice(start, stop);
  const value = masked(entry.join('').slice(indent + 'exempt'.length)).replace(/\r\n?/g, '\n');
  if (NODE_PROPERTY.test(value)) throw new ExemptNotMigratable();
  const rest = [...lines.slice(0, start), ...lines.slice(stop)];
  const body = rest.slice(key + 1);
  if (!body.slice(0, bodyEnd(body)).some((line) => !blank(line) && !comment(line) && indentOf(line) > 0)) {
    rest.splice(key, 1);
  }
  const formats = rest.flatMap((line, i) => (FORMAT_LINE.test(line) ? [i] : []));
  if (formats.length !== 1) throw new ExemptNotMigratable();
  const at = formats[0] as number;
  const ending = /\r?\n$/.exec(rest[at] as string)?.[0];
  const newline = ending ?? '\n';
  const moved = entry.map((line) => dedent(line, indent)).map((line) => (/[\r\n]$/.test(line) ? line : line + newline));
  if (ending === undefined) rest[at] += newline;
  const result = [...rest.slice(0, at + 1), ...moved, ...rest.slice(at + 1)].join('');
  let migrated: unknown;
  try {
    migrated = loadYaml(result);
  } catch (error) {
    if (error instanceof YAMLError) throw new ExemptNotMigratable();
    throw error;
  }
  if (!isDeepStrictEqual(normalize(migrated), normalize(expected(data, current)))) throw new ExemptNotMigratable();
  return result;
}
