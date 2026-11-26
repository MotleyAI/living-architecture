// JSON text as Python's json.dumps writes it: ASCII-only, floats in repr, `indent` like Python's.
import { PyFloat, reprFloat } from './values.js';

function str(text: string): string {
  return JSON.stringify(text).replace(/[\u007f-￿]/g, (ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

function scalar(value: unknown): string | undefined {
  if (value === null || value === undefined) return 'null';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'string') return str(value);
  if (typeof value === 'bigint') return value.toString();
  if (value instanceof PyFloat) {
    if (Number.isNaN(value.value)) return 'NaN';
    if (!Number.isFinite(value.value)) return value.value > 0 ? 'Infinity' : '-Infinity';
    return reprFloat(value.value);
  }
  if (typeof value === 'number') return String(value);
  return undefined;
}

export function pyJson(value: unknown, indent?: number, level = 0): string {
  const text = scalar(value);
  if (text !== undefined) return text;
  const entries: [string | null, unknown][] = Array.isArray(value)
    ? value.map((v) => [null, v])
    : Object.entries(value as object);
  const [open, close] = Array.isArray(value) ? ['[', ']'] : ['{', '}'];
  if (entries.length === 0) return open + close;
  const item = ([k, v]: [string | null, unknown]): string =>
    (k === null ? '' : `${str(k)}: `) + pyJson(v, indent, level + 1);
  if (indent === undefined) return open + entries.map(item).join(', ') + close;
  const pad = ' '.repeat(indent * (level + 1));
  return `${open}\n${entries.map((e) => pad + item(e)).join(',\n')}\n${' '.repeat(indent * level)}${close}`;
}
