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

function sexagesimal(digits: string): bigint {
  return digits.split(':').reduce((acc, part) => acc * 60n + BigInt(part), 0n);
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
  else value = BigInt(text);
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
  if (text === '.nan') return new PyFloat(NaN);
  if (text.includes(':')) {
    const parts = text.split(':').map(Number);
    return new PyFloat(sign * parts.reduce((acc, part) => acc * 60 + part, 0));
  }
  return new PyFloat(sign * Number(text));
}

const pad = (value: string | number, width = 2): string => String(value).padStart(width, '0');

function resolveTimestamp(source: string): PyTimestamp {
  const m = TIMESTAMP_PARTS_RE.exec(source);
  if (m === null) return new PyTimestamp(source);
  const [, year, month, day, hour, minute, second, fraction, tz, tzSign, tzHour, tzMinute] = m;
  const date = `${year}-${pad(month ?? '')}-${pad(day ?? '')}`;
  if (hour === undefined) return new PyTimestamp(date);
  let iso = `${date}T${pad(hour)}:${minute}:${second}`;
  const micro = (fraction ?? '').slice(0, 6).padEnd(6, '0');
  if (Number(micro) !== 0) iso += `.${micro}`;
  if (tz === 'Z') iso += '+00:00';
  else if (tzSign !== undefined) iso += `${tzSign}${pad(tzHour ?? '')}:${pad(tzMinute ?? '0')}`;
  return new PyTimestamp(iso);
}

const scalar = (tag: string, test: RegExp, resolve: (text: string) => unknown): ScalarTag => ({
  tag: `tag:yaml.org,2002:${tag}`,
  default: true,
  test,
  resolve,
});

const PROFILE_TAGS: ScalarTag[] = [
  scalar('bool', BOOL_RE, (text) => ['yes', 'true', 'on'].includes(text.toLowerCase())),
  scalar('null', NULL_RE, () => null),
  scalar('int', INT_RE, resolveInt),
  scalar('float', FLOAT_RE, resolveFloat),
  scalar('timestamp', TIMESTAMP_RE, resolveTimestamp),
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
  const problem = doc.errors[0];
  if (problem !== undefined) throw new YAMLError(problem.message);
  try {
    return doc.toJS({ mapAsMap: true, maxAliasCount: -1 });
  } catch (error) {
    if (error instanceof LibYAMLError || error instanceof Error) throw new YAMLError(error.message);
    throw error;
  }
}
