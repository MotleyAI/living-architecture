// The shared YAML profile: YAML 1.1 as PyYAML's safe loader reads it (its implicit resolvers, merge keys, the last
// duplicate key wins). Mappings load as Maps, floats as PyFloat, timestamps as PyTimestamp.
import { YAMLError as LibYAMLError, parseAllDocuments, type ScalarTag } from 'yaml';
import { PyFloat, PyTimestamp } from './values.js';

export class YAMLError extends Error {}

const BOOL_RE = /^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$/;
const NULL_RE = /^(?:~|null|Null|NULL|)$/;
const INT_RE =
  /^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$/;
const FLOAT_RE =
  /^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$/;
const TIMESTAMP_RE =
  /^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$/;
const TIMESTAMP_PARTS_RE =
  /^([0-9][0-9][0-9][0-9])-([0-9][0-9]?)-([0-9][0-9]?)(?:(?:[Tt]|[ \t]+)([0-9][0-9]?):([0-9][0-9]):([0-9][0-9])(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9][0-9]?)(?::([0-9][0-9]))?))?)?$/;

function integer(text: string): number | bigint {
  const big = BigInt(text);
  return big >= BigInt(Number.MIN_SAFE_INTEGER) && big <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(big) : big;
}

// Python's default cap on decimal integer string conversion (sys.int_info.default_max_str_digits).
const MAX_DECIMAL_DIGITS = 4300;

/** An ASCII decimal digit string as a bigint, refused beyond Python's digit cap. */
function decimal(digits: string): bigint {
  if (digits.length > MAX_DECIMAL_DIGITS) {
    throw new ConstructError(`exceeds the limit (${MAX_DECIMAL_DIGITS} digits) for integer string conversion`);
  }
  return BigInt(digits);
}

function sexagesimal(digits: string): bigint {
  return digits.split(':').reduce((acc, part) => acc * 60n + decimal(part), 0n);
}

function resolveInt(source: string): number | bigint {
  let text = source.replaceAll('_', '');
  let sign = 1n;
  if (text.startsWith('-') || text.startsWith('+')) {
    if (text.startsWith('-')) sign = -1n;
    text = text.slice(1);
  }
  let value: bigint;
  if (text === '0') value = 0n;
  else if (text.startsWith('0b')) value = BigInt(`0b${text.slice(2)}`);
  else if (text.startsWith('0x')) value = BigInt(`0x${text.slice(2)}`);
  else if (text.startsWith('0')) value = BigInt(`0o${text.slice(1)}`);
  else if (text.includes(':')) value = sexagesimal(text);
  else value = decimal(text);
  return integer((sign * value).toString());
}

function resolveFloat(source: string): PyFloat {
  let text = source.replaceAll('_', '').toLowerCase();
  let sign = 1;
  if (text.startsWith('-') || text.startsWith('+')) {
    if (text.startsWith('-')) sign = -1;
    text = text.slice(1);
  }
  if (text === '.inf') return new PyFloat(sign * Infinity);
  if (text === '.nan') return new PyFloat(Number.NaN);
  if (text.includes(':')) {
    const parts = text.split(':').map(Number);
    return new PyFloat(sign * parts.reduce((acc, part) => acc * 60 + part, 0));
  }
  return new PyFloat(sign * Number(text));
}

const pad = (value: string | number, width = 2): string => String(value).padStart(width, '0');

/** Thrown by a constructor for a scalar PyYAML's safe loader cannot construct. */
class ConstructError extends Error {}

function daysIn(year: number, month: number): number {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function checkRange(name: string, value: number, low: number, high: number): void {
  if (value < low || value > high) throw new ConstructError(`${name} must be in ${low}..${high}, not ${value}`);
}

function resolveTimestamp(source: string): PyTimestamp {
  // Python's `$` also matches before a final newline, as an explicitly tagged block scalar ends.
  const m = TIMESTAMP_PARTS_RE.exec(source.endsWith('\n') ? source.slice(0, -1) : source);
  if (m === null) throw new ConstructError(`not a timestamp: ${source}`);
  const [, year, month, day, hour, minute, second, fraction, tz, tzSign, tzHour, tzMinute] = m;
  checkRange('year', Number(year), 1, 9999);
  checkRange('month', Number(month), 1, 12);
  checkRange('day', Number(day), 1, daysIn(Number(year), Number(month)));
  const date = `${year}-${pad(month ?? '')}-${pad(day ?? '')}`;
  if (hour === undefined) return new PyTimestamp(date);
  checkRange('hour', Number(hour), 0, 23);
  checkRange('minute', Number(minute), 0, 59);
  checkRange('second', Number(second), 0, 59);
  let iso = `${date}T${pad(hour)}:${minute}:${second}`;
  const micro = (fraction ?? '').slice(0, 6).padEnd(6, '0');
  if (Number(micro) !== 0) iso += `.${micro}`;
  if (tz === 'Z') iso += '+00:00';
  else if (tzSign !== undefined) {
    const offset = (Number(tzHour) * 60 + Number(tzMinute ?? '0')) * (tzSign === '-' ? -1 : 1);
    if (Math.abs(offset) >= 24 * 60) throw new ConstructError(`offset must be strictly within 24 hours: ${source}`);
    iso += `${offset < 0 ? '-' : '+'}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`;
  }
  return new PyTimestamp(iso);
}

// Python's str.isspace() code points, which int() and float() strip.
const PY_SPACE: [number, number][] = [
  [0x09, 0x0d],
  [0x1c, 0x20],
  [0x85, 0x85],
  [0xa0, 0xa0],
  [0x1680, 0x1680],
  [0x2000, 0x200a],
  [0x2028, 0x2029],
  [0x202f, 0x202f],
  [0x205f, 0x205f],
  [0x3000, 0x3000],
];
const DECIMAL_DIGIT = /^\p{Nd}$/u;

function isPySpace(char: string | undefined): boolean {
  const code = char?.codePointAt(0) ?? -1;
  return PY_SPACE.some(([low, high]) => code >= low && code <= high);
}

function pyStrip(text: string): string {
  const chars = [...text];
  let start = 0;
  let end = chars.length;
  while (start < end && isPySpace(chars[start])) start += 1;
  while (end > start && isPySpace(chars[end - 1])) end -= 1;
  return chars.slice(start, end).join('');
}

/** A digit's value as Python's int() reads it (any Unicode decimal digit, ASCII letters from 10), else 99. */
function digitValue(char: string): number {
  const code = char.codePointAt(0) ?? 0;
  if (DECIMAL_DIGIT.test(char)) {
    // Unicode decimal digits come in contiguous runs of whole 0..9 sequences.
    let zero = code;
    while (DECIMAL_DIGIT.test(String.fromCodePoint(zero - 1))) zero -= 1;
    return (code - zero) % 10;
  }
  return /^[a-zA-Z]$/.test(char) ? (char.toLowerCase().codePointAt(0) ?? 0) - 87 : 99;
}

const INT_PREFIX = { 2: '0b', 8: '0o', 10: '', 16: '0x' } as const;

/** Python's `int(text, base)`. */
function pyInt(source: string, base: 2 | 8 | 10 | 16): bigint {
  let text = pyStrip(source);
  const negative = text.startsWith('-');
  if (negative || text.startsWith('+')) text = text.slice(1);
  const prefix = INT_PREFIX[base];
  if (prefix !== '' && text.toLowerCase().startsWith(prefix)) text = text.slice(2);
  const values = [...text].map(digitValue);
  if (values.length === 0 || values.some((value) => value >= base)) {
    throw new ConstructError(`invalid literal for int() with base ${base}: '${source}'`);
  }
  const value = base === 10 ? decimal(values.join('')) : values.reduce((acc, digit) => acc * BigInt(base) + BigInt(digit), 0n);
  return negative ? -value : value;
}

const PY_DECIMAL_RE = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/;
const PY_FLOAT_WORDS = new Map([['inf', Infinity], ['infinity', Infinity], ['nan', Number.NaN]]);

/** Python's `float(text)`. */
function pyFloat(source: string): number {
  const ascii = [...pyStrip(source)].map((char) => (DECIMAL_DIGIT.test(char) ? String(digitValue(char)) : char));
  const [body, negative] = unsigned(ascii.join('').toLowerCase());
  const magnitude = PY_FLOAT_WORDS.get(body) ?? (PY_DECIMAL_RE.test(body) ? Number(body) : undefined);
  if (magnitude === undefined) throw new ConstructError(`could not convert string to float: '${source}'`);
  return negative ? -magnitude : magnitude;
}

/** `text` without one leading sign, and that sign. */
function unsigned(text: string): [string, boolean] {
  return text.startsWith('-') || text.startsWith('+') ? [text.slice(1), text.startsWith('-')] : [text, false];
}

/** An explicit `!!int`, as PyYAML's constructor reads any text. */
function constructInt(source: string): number | bigint {
  const [text, negative] = unsigned(source.replaceAll('_', ''));
  let value: bigint;
  if (text === '0') value = 0n;
  else if (text.startsWith('0b')) value = pyInt(text.slice(2), 2);
  else if (text.startsWith('0x')) value = pyInt(text.slice(2), 16);
  else if (text.startsWith('0')) value = pyInt(text, 8);
  else if (text.includes(':')) value = text.split(':').reduce((acc, part) => acc * 60n + pyInt(part, 10), 0n);
  else value = pyInt(text, 10);
  return integer((negative ? -value : value).toString());
}

/** An explicit `!!float`, as PyYAML's constructor reads any text. */
function constructFloat(source: string): PyFloat {
  const [text, negative] = unsigned(source.replaceAll('_', '').toLowerCase());
  const sign = negative ? -1 : 1;
  if (text === '.inf') return new PyFloat(sign * Infinity);
  if (text === '.nan') return new PyFloat(Number.NaN);
  if (text.includes(':')) return new PyFloat(sign * text.split(':').reduce((acc, part) => acc * 60 + pyFloat(part), 0));
  return new PyFloat(sign * pyFloat(text));
}

const BOOLS = new Map([['yes', true], ['no', false], ['true', true], ['false', false], ['on', true], ['off', false]]);

/** An explicit `!!bool`, as PyYAML's constructor reads any text. */
function constructBool(source: string): boolean {
  const value = BOOLS.get(source.toLowerCase());
  if (value === undefined) throw new ConstructError(`not a boolean: '${source}'`);
  return value;
}

type Construct = (text: string) => unknown;

/** A resolver that reports a ConstructError as a YAML error rather than a crash. */
const reporting =
  (construct: Construct) =>
  (text: string, onError: (message: string) => void): unknown => {
    try {
      return construct(text);
    } catch (error) {
      if (!(error instanceof ConstructError)) throw error;
      onError(error.message);
      return text;
    }
  };

const TAG = (name: string): string => `tag:yaml.org,2002:${name}`;

/** An implicitly resolved scalar type. */
const implicit = (name: string, test: RegExp, construct: Construct): ScalarTag => ({
  tag: TAG(name),
  default: true,
  test,
  resolve: reporting(construct),
});

/** The constructor an explicit `!!name` tag uses whatever the text; listed first, it wins over the implicit one. */
const explicit = (name: string, construct: Construct): ScalarTag => ({ tag: TAG(name), resolve: reporting(construct) });

const PROFILE_TAGS: ScalarTag[] = [
  explicit('bool', constructBool),
  explicit('null', () => null),
  explicit('int', constructInt),
  explicit('float', constructFloat),
  explicit('timestamp', resolveTimestamp),
  implicit('bool', BOOL_RE, (text) => ['yes', 'true', 'on'].includes(text.toLowerCase())),
  implicit('null', NULL_RE, () => null),
  implicit('int', INT_RE, resolveInt),
  implicit('float', FLOAT_RE, resolveFloat),
  implicit('timestamp', TIMESTAMP_RE, resolveTimestamp),
];

/** The first document of `text` in the shared profile (null when empty); YAMLError when invalid. */
export function loadYaml(text: string): unknown {
  let docs;
  try {
    docs = parseAllDocuments(text, { schema: 'failsafe', customTags: PROFILE_TAGS, merge: true, uniqueKeys: false });
  } catch (error) {
    throw new YAMLError(String(error));
  }
  if (docs.length > 1) throw new YAMLError('expected a single document in the stream');
  const [doc] = docs;
  if (doc === undefined) return null;
  // An unresolved tag is only a warning to the library; PyYAML's safe loader cannot construct it.
  const problem = doc.errors[0] ?? doc.warnings.find((warning) => warning.code === 'TAG_RESOLVE_FAILED');
  if (problem !== undefined) throw new YAMLError(problem.message);
  try {
    return doc.toJS({ mapAsMap: true, maxAliasCount: -1 });
  } catch (error) {
    if (error instanceof LibYAMLError || error instanceof Error) throw new YAMLError(error.message);
    throw error;
  }
}
