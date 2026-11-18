// Word tables: a vocabulary rename's words, its carve-outs and hand-written entries, and the names they rename.
import { globMatch, message, schema, validate } from '../contract/index.js';
import { words } from './compound.js';
import { type MapEntry, MapError, yamlDocument } from './map.js';

/** Each `from` of a table and its `to`. */
export type Words = Record<string, string>;

/** Where words keep their old sense: by a written annotation's identifier, the declaring file's path, or a symbol. */
export interface CarveOut {
  words: string[];
  annotated?: string[];
  paths?: string[];
  symbols?: { file: string; symbol: string }[];
}

/** A word table as written, `shown` in messages. */
export interface WordTable {
  shown: string;
  words: Words;
  carveOuts: CarveOut[];
  entries: MapEntry[];
}

/** What a carve-out is matched against: the declaring file, the written annotation, and the declaration's keys. */
export interface Carvable {
  rel: string;
  annotation: string | null;
  keys: string[];
}

const IDENTIFIER = /[\p{ID_Start}$_][\p{ID_Continue}$‌‍]*/gu;
const ROW = { from: 'a', to: 'b' };

interface Held {
  start: number;
  end: number;
  word: string;
  from: string;
}

/** The words of `name` that are a `from` of `table`, compared without case, with their spans. */
function held(name: string, table: Words): Held[] {
  const out: Held[] = [];
  let position = 0;
  for (const word of words(name)) {
    const start = name.indexOf(word, position);
    position = start + word.length;
    const from = word.toLowerCase();
    if (Object.hasOwn(table, from)) out.push({ start, end: position, word, from });
  }
  return out;
}

/** The `from`s `name` holds as whole words, in the order it first spells them. */
export function heldWords(name: string, table: Words): string[] {
  return [...new Set(held(name, table).map((h) => h.from))];
}

/** `to` in the case form of `word`: capitals, capitalized or lowercase. */
function cased(word: string, to: string): string {
  if ([...word].length > 1 && !/\p{Ll}/u.test(word)) return to.toUpperCase();
  return /^\p{Lu}/u.test(word) ? to.slice(0, 1).toUpperCase() + to.slice(1) : to;
}

/** `name` with each held word replaced once by its `to`, every other character unchanged. */
export function replaceWords(name: string, table: Words): string {
  let out = '';
  let position = 0;
  for (const h of held(name, table)) {
    out += name.slice(position, h.start) + cased(h.word, table[h.from] ?? '');
    position = h.end;
  }
  return out + name.slice(position);
}

/** `table` without the words of `dropped`. */
export function withoutWords(table: Words, dropped: Iterable<string>): Words {
  const gone = new Set(dropped);
  return Object.fromEntries(Object.entries(table).filter(([from]) => !gone.has(from)));
}

const isMapping = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const valid = (document: unknown): boolean => validate(schema('word-table'), document).length === 0;

/** The table at `path` (`shown` in messages); MapError naming every invalid item by section and 1-based index, `words`
 * item 1 for a file that holds no table. */
export function loadWordTable(path: string, shown: string): WordTable {
  const invalid = (items: [string, number][]): MapError =>
    new MapError(items.map(([section, index]) => message('refactor.words-invalid', { table: shown, section, index })).join('\n'));
  const data = yamlDocument(path);
  if (!isMapping(data) || !Array.isArray(data.words) || data.words.length === 0) throw invalid([['words', 1]]);
  const bad: [string, number][] = [];
  const table: Words = {};
  for (const [i, row] of (data.words as unknown[]).entries()) {
    const { from, to } = (isMapping(row) ? row : {}) as { from?: string; to?: string };
    if (valid({ words: [row] }) && from !== undefined && to !== undefined && from !== to && !Object.hasOwn(table, from)) table[from] = to;
    else bad.push(['words', i + 1]);
  }
  for (const section of ['carve_outs', 'entries']) if (data[section] !== undefined && !Array.isArray(data[section])) bad.push([section, 1]);
  const carveOuts = Array.isArray(data.carve_outs) ? (data.carve_outs as CarveOut[]) : [];
  for (const [i, item] of carveOuts.entries()) {
    const known = valid({ words: [ROW], carve_outs: [item] }) && item.words.every((word) => Object.hasOwn(table, word));
    if (!known) bad.push(['carve_outs', i + 1]);
  }
  const entries = Array.isArray(data.entries) ? (data.entries as MapEntry[]) : [];
  for (const [i, entry] of entries.entries()) if (validate(schema('rename-map'), [entry]).length > 0) bad.push(['entries', i + 1]);
  if (bad.length > 0) throw invalid(bad);
  if (!valid(data)) throw invalid([['words', 1]]);
  return { shown, words: table, carveOuts, entries };
}

/** The identifier tokens of a written annotation. */
export const annotationNames = (annotation: string): Set<string> => new Set(annotation.match(IDENTIFIER) ?? []);

/** A declaration's key in a carve-out's located symbols. */
export const carveKey = (file: string, position: number): string => `${file}\0${position}`;

/** How `carve` matches `found`: its key with the listed value that matched; null when it does not. `located` holds the
 * keys its `symbols` locate. */
function matcher(carve: CarveOut, located: Set<string>, found: Carvable): string | null {
  if (carve.annotated !== undefined) {
    const names = found.annotation === null ? new Set<string>() : annotationNames(found.annotation);
    const name = carve.annotated.find((listed) => names.has(listed));
    return name === undefined ? null : `annotated ${name}`;
  }
  if (carve.paths !== undefined) {
    const glob = carve.paths.find((listed) => globMatch(listed, found.rel));
    return glob === undefined ? null : `paths ${glob}`;
  }
  return found.keys.some((key) => located.has(key)) ? 'symbols' : null;
}

/** The first carve-out of `table`, in its order, that keeps `word` for `found`, as `refactor.carved` names it; null
 * when none does. `located[i]` holds the keys the symbols of carve-out `i` locate. */
export function carved(table: WordTable, located: Set<string>[], word: string, found: Carvable): string | null {
  for (const [i, carve] of table.carveOuts.entries()) {
    if (!carve.words.includes(word)) continue;
    const match = matcher(carve, located[i] ?? new Set(), found);
    if (match !== null) return match;
  }
  return null;
}

