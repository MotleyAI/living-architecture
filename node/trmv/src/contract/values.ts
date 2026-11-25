// Values as the shared YAML profile yields them, and their canonical repr (Python's repr).

/** A YAML float: keeps `1.0` distinct from the integer `1`. */
export class PyFloat {
  constructor(readonly value: number) {}

  valueOf(): number {
    return this.value;
  }
}

/** A YAML timestamp, held as the ISO text it normalizes to. */
export class PyTimestamp {
  constructor(readonly iso: string) {}

  toString(): string {
    return this.iso;
  }
}

/** A mapping keeps non-string keys, so it is a Map. */
export type PyMapping = Map<unknown, unknown>;

/** Map a raw YAML value onto the normalized types (string, int, float, bool, null, list, mapping). */
export function normalize(value: unknown): unknown {
  if (value instanceof PyTimestamp) return value.iso;
  if (Array.isArray(value)) return value.map(normalize);
  if (value instanceof Map) return new Map([...value].map(([k, v]) => [normalize(k), normalize(v)]));
  return value;
}

const NOT_PRINTABLE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]/u;

function escapeChar(ch: string, quote: string): string {
  if (ch === '\\' || ch === quote) return `\\${ch}`;
  if (ch === '\t') return '\\t';
  if (ch === '\n') return '\\n';
  if (ch === '\r') return '\\r';
  if (ch === ' ' || !NOT_PRINTABLE.test(ch)) return ch;
  const code = ch.codePointAt(0) ?? 0;
  if (code < 0x100) return `\\x${code.toString(16).padStart(2, '0')}`;
  if (code < 0x10000) return `\\u${code.toString(16).padStart(4, '0')}`;
  return `\\U${code.toString(16).padStart(8, '0')}`;
}

function reprString(text: string): string {
  const quote = text.includes("'") && !text.includes('"') ? '"' : "'";
  return quote + [...text].map((ch) => escapeChar(ch, quote)).join('') + quote;
}

/** Python's float repr: shortest round-trip digits, fixed notation for exponents in [-4, 16). */
export function reprFloat(x: number): string {
  if (Number.isNaN(x)) return 'nan';
  if (!Number.isFinite(x)) return x > 0 ? 'inf' : '-inf';
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
  const [mantissa = '', exp = '0'] = x.toExponential().split('e');
  const sign = mantissa.startsWith('-') ? '-' : '';
  const digits = mantissa.replace('-', '').replace('.', '');
  const decpt = Number(exp) + 1;
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) return `${sign}0.${'0'.repeat(-decpt)}${digits}`;
    if (decpt >= digits.length) return `${sign}${digits}${'0'.repeat(decpt - digits.length)}.0`;
    return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`;
  }
  const e = decpt - 1;
  const body = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
  return `${sign}${body}e${e < 0 ? '-' : '+'}${String(Math.abs(e)).padStart(2, '0')}`;
}

/** Python's `f"{x:.1f}"` for finite x: exact ties (x.25, x.75) round half to even, unlike toFixed. */
export function fixed1(x: number): string {
  const quarters = x * 4;
  if (!Number.isInteger(quarters) || quarters % 2 === 0) return x.toFixed(1);
  const down = Math.floor(x * 10);
  const n = down % 2 === 0 ? down : down + 1;
  const sign = n < 0 ? '-' : '';
  return `${sign}${Math.trunc(Math.abs(n) / 10)}.${Math.abs(n) % 10}`;
}

/** Python's repr, restricted to normalized values. */
export function canonicalRepr(value: unknown): string {
  if (value === null || value === undefined) return 'None';
  if (value === true) return 'True';
  if (value === false) return 'False';
  if (typeof value === 'string') return reprString(value);
  if (typeof value === 'bigint') return value.toString();
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : reprFloat(value);
  if (value instanceof PyFloat) return reprFloat(value.value);
  if (value instanceof PyTimestamp) return reprString(value.iso);
  if (Array.isArray(value)) return `[${value.map(canonicalRepr).join(', ')}]`;
  if (value instanceof Map) {
    return `{${[...value].map(([k, v]) => `${canonicalRepr(k)}: ${canonicalRepr(v)}`).join(', ')}}`;
  }
  if (typeof value === 'object') {
    return `{${Object.entries(value).map(([k, v]) => `${canonicalRepr(k)}: ${canonicalRepr(v)}`).join(', ')}}`;
  }
  throw new TypeError(`not a normalized value: ${typeof value}`);
}

/** A loaded value as plain data: Maps become objects (string keys), floats and timestamps their primitives. */
export function toPlain(value: unknown): any {
  if (value instanceof PyFloat) return value.value;
  if (value instanceof PyTimestamp) return value.iso;
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [String(toPlain(k)), toPlain(v)]));
  return value;
}
