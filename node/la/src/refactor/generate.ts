// `dr-refactor generate-map TABLE`: a rename map for a word table, read from the TypeScript sources' syntax alone.
import { existsSync, statSync } from 'node:fs';
import { basename } from 'node:path';
import type * as TS from 'typescript';
import { languageIds, languageOf, loadYaml, message, readFile, toPlain } from '../contract/index.js';
import { stripSourceExtension, ts } from '../lang/index.js';
import * as twin from '../twin/index.js';
import { annotationOf, declaredName, locateCarveSymbols } from './carve.js';
import { RefactorError } from './edits.js';
import { Lines } from './lines.js';
import { entrySource, type MapEntry, MapError } from './map.js';
import { refusal, Refused } from './progress.js';
import { languageFiles } from './routing.js';
import { nodeAt, positionOf, type Refactor } from './session.js';
import { locate, locateEvery, LocatorError, reach, type Reached } from './symbols.js';
import { type Carvable, carved, carveKey, heldWords, loadWordTable, replaceWords, withoutWords, type WordTable } from './words.js';

const PLAIN = /^[A-Za-z0-9_$./<>()-]+$/u;
const KEYS = ['module', 'file', 'symbol', 'line', 'col', 'offset', 'new_name', 'retarget'] as const;

/** A declaration a rename can locate: its name's span, every declaration of its symbol, and its path when the path
 * locates exactly it. */
interface Candidate {
  name: string;
  start: number;
  positions: number[];
  path: string | null;
  local: boolean;
  node: TS.Node;
}

/** A name span an entry of the table locates. */
interface Site {
  file: string;
  start: number;
  end: number;
}

/** An import or export binding: its path would follow to what it names. */
const binds = (node: TS.Node): boolean =>
  ts().isImportSpecifier(node) || ts().isExportSpecifier(node) || ts().isImportClause(node) || ts().isNamespaceImport(node) || ts().isNamespaceExport(node) || ts().isImportEqualsDeclaration(node);

/** The candidates of `source`, one per symbol at its first declaration, in source order. */
function candidates(source: TS.SourceFile): Candidate[] {
  const reached = new Map<number, Reached>();
  for (const found of reach(source)) for (const name of found.names) reached.set(name.getStart(source), found);
  const out: Candidate[] = [];
  const visit = (node: TS.Node): void => {
    const name = declaredName(node);
    const start = name?.getStart(source) ?? -1;
    const found = reached.get(start);
    if (name !== undefined && found === undefined) out.push({ name: name.text, start, positions: [start], path: null, local: false, node });
    else if (name !== undefined && found?.names[0]?.getStart(source) === start) {
      const positions = found.names.map((n) => n.getStart(source));
      out.push({ name: name.text, start, positions, path: binds(node) ? null : found.path, local: found.local && !found.parameter, node });
    }
    ts().forEachChild(node, visit);
  };
  visit(source);
  return out.sort((a, b) => a.start - b.start);
}

/** A map value as YAML: plain when it reads back as itself, else single-quoted. */
function scalar(value: string | number): string {
  if (typeof value === 'number') return String(value);
  let plain = PLAIN.test(value);
  try {
    plain = plain && toPlain(loadYaml(value)) === value;
  } catch {
    plain = false;
  }
  return plain ? value : `'${value.replaceAll("'", "''")}'`;
}

const field = (key: string, value: string | number | undefined): string[] => (value === undefined ? [] : [`${key}: ${scalar(value)}`]);

const line = (entry: MapEntry): string => `- {${KEYS.flatMap((key) => field(key, entry[key])).join(', ')}}\n`;

/** The project's sources, parsed once. */
class Sources {
  private readonly parsed = new Map<string, TS.SourceFile>();

  /** The source at `path`, null when it is no file. */
  get(path: string): TS.SourceFile | null {
    let source = this.parsed.get(path);
    if (source === undefined) {
      if (!existsSync(path) || !statSync(path).isFile()) return null;
      source = ts().createSourceFile(path, readFile(path, 'utf8'), ts().ScriptTarget.Latest, true);
      this.parsed.set(path, source);
    }
    return source;
  }
}

/** The name spans entry `entry` locates, a module entry its whole file (`end` 0); an error naming what its locator
 * does not resolve to. */
function entrySites(r: Refactor, sources: Sources, entry: MapEntry): Site[] {
  const shown = entry.module ?? entry.file ?? '';
  const file = r.inProject(shown, r.root);
  const source = sources.get(file);
  if (source === null) throw new MapError(message('refactor.source-missing', { path: shown }));
  if (entry.module !== undefined) return [{ file, start: 0, end: 0 }];
  const position = positionOf(source.text, entry);
  let positions = position === null ? [] : [position];
  if (entry.symbol !== undefined) {
    const found = entry.retarget === undefined ? locateEvery(null, source, entry.symbol, shown) : [locate(null, source, entry.symbol, shown, false)];
    positions = found.map((located) => located.position);
  }
  return positions.flatMap((at) => {
    const node = nodeAt(source, at);
    return ts().isIdentifier(node) || ts().isPrivateIdentifier(node) ? [{ file, start: node.getStart(source), end: node.end }] : [];
  });
}

/** The first entry's failure to resolve, as exit 2. */
function located(r: Refactor, sources: Sources, table: WordTable): Site[] {
  try {
    return table.entries.flatMap((entry) => entrySites(r, sources, entry));
  } catch (error) {
    if (error instanceof RefactorError || error instanceof LocatorError || error instanceof MapError) throw new Refused([refusal(error.message, 2)]);
    throw error;
  }
}

interface Row {
  candidate: Candidate;
  taken: boolean;
  kept: [string, string][];
  held: number;
  line: number;
  col: number;
}

interface Ordered {
  path: string;
  line: number;
  position: number;
  text: string;
}

const inOrder = (a: Ordered, b: Ordered, byLine: boolean): number => {
  if (a.path !== b.path) return a.path < b.path ? -1 : 1;
  return (byLine ? a.line - b.line : 0) || a.position - b.position;
};

/** One file's rows: each candidate holding a word, with what locates and keeps it. */
function rows(source: TS.SourceFile, rel: string, table: WordTable, carves: Set<string>[], taken: Site[]): Row[] {
  const lines = new Lines(source.text);
  return candidates(source).flatMap((candidate) => {
    const held = heldWords(candidate.name, table.words);
    if (held.length === 0) return [];
    const found: Carvable = { rel, annotation: annotationOf(candidate.node, source), keys: candidate.positions.map((p) => carveKey(source.fileName, p)) };
    const kept = held.flatMap((word): [string, string][] => {
      const matcher = carved(table, carves, word, found);
      return matcher === null ? [] : [[word, matcher]];
    });
    const row = lines.lineOf(candidate.start);
    const col = [...source.text.substring(lines.start(row), candidate.start)].length + 1;
    const isTaken = candidate.positions.some((p) => taken.some((site) => site.start <= p && p <= site.end));
    return [{ candidate, taken: isTaken, kept, held: held.length, line: row, col }];
  });
}

interface Output {
  generated: Ordered[];
  listed: Ordered[];
}

/** The module entry of the file `rel` named `stem`, each word of its name a carve-out keeps listed. */
function fileModule(rel: string, stem: string, table: WordTable, out: Output): void {
  const keptWords: string[] = [];
  for (const word of heldWords(stem, table.words)) {
    const matcher = carved(table, [], word, { rel, annotation: null, keys: [] });
    if (matcher === null) continue;
    keptWords.push(word);
    out.listed.push({ path: rel, line: 0, position: 0, text: message('refactor.carved', { path: rel, line: 1, name: stem, word, matcher }) });
  }
  const renamed = replaceWords(stem, withoutWords(table.words, keptWords));
  if (renamed !== stem) out.generated.push({ path: rel, line: 0, position: 0, text: line({ module: rel, new_name: renamed }) });
}

/** The locals one wildcard entry stands for with `row`: two or more of its name, each located by its path, none
 * located by an entry or kept; empty when `row` is written alone. */
function wildGroup(found: Row[], row: Row): Row[] {
  const { candidate } = row;
  if (!candidate.local) return [];
  const group = found.filter((other) => other.candidate.local && other.candidate.name === candidate.name);
  return group.length > 1 && group.every((other) => other.candidate.path !== null && !other.taken && other.kept.length === 0) ? group : [];
}

/** The entries of the declarations `found` in `rel`, each kept word listed. */
function fileDeclarations(rel: string, found: Row[], table: WordTable, out: Output): void {
  for (const row of found.filter((each) => !each.taken)) {
    const { candidate } = row;
    for (const [word, matcher] of row.kept) {
      out.listed.push({ path: rel, line: row.line, position: candidate.start, text: message('refactor.carved', { path: rel, line: row.line, name: candidate.name, word, matcher }) });
    }
    if (row.kept.length === row.held) continue;
    const group = wildGroup(found, row);
    if (group.length > 0 && group[0] !== row) continue;
    const symbol = group.length > 0 ? `*.<locals>.${candidate.name}` : candidate.path;
    const newName = replaceWords(candidate.name, withoutWords(table.words, row.kept.map(([word]) => word)));
    const entry: MapEntry = symbol === null ? { file: rel, line: row.line, col: row.col, new_name: newName } : { file: rel, symbol, new_name: newName };
    out.generated.push({ path: rel, line: row.line, position: candidate.start, text: line(entry) });
  }
}

/** MapError unless every entry of `table` is of the generated language. */
function checkLanguage(table: WordTable, shown: string): void {
  const native = twin.NATIVE_LANGUAGE;
  const languages = table.entries.map((entry) => languageOf(entrySource(entry)));
  if (languages.every((id) => id === native)) return;
  const ids = languageIds().filter((id) => id === native || languages.includes(id));
  throw new MapError(message('refactor.map-mixed-languages', { map: shown, languages: ids.join(', ') }));
}

/** `generate-map`: the table's entries, then one entry per candidate, on stdout; what is left out on stderr; 0, or 1
 * when the map is empty. */
export function generateMap(r: Refactor): number {
  const shown = r.args.table ?? '';
  const table = loadWordTable(shown, shown);
  checkLanguage(table, shown);
  const sources = new Sources();
  const carves = locateCarveSymbols(table, (file, symbol) => {
    const source = sources.get(r.inProject(file, r.root));
    if (source === null) throw new LocatorError(message('refactor.symbol-unresolved', { path: file, symbol, candidates: '' }));
    return locate(null, source, symbol, file, false);
  });
  const taken = located(r, sources, table);
  const out: Output = { generated: [], listed: [] };
  for (const path of languageFiles(r.root, twin.NATIVE_LANGUAGE)) {
    const source = sources.get(path);
    if (source === null) continue;
    const rel = r.rel(path);
    const named = taken.some((site) => site.file === path && site.end === 0);
    if (!named) fileModule(rel, stripSourceExtension(basename(path)), table, out);
    const found = rows(source, rel, table, carves, taken.filter((site) => site.file === path && site.end > 0));
    fileDeclarations(rel, found, table, out);
  }
  const map = [...table.entries.map(line), ...out.generated.toSorted((a, b) => inOrder(a, b, false)).map((entry) => entry.text)];
  const empty = map.length === 0 ? [message('refactor.generate-empty', { table: shown })] : [];
  const listed = out.listed.toSorted((a, b) => inOrder(a, b, true)).map((item) => item.text);
  process.stderr.write([...listed, ...empty].map((text) => `${text}\n`).join(''));
  process.stdout.write(map.join(''));
  return map.length === 0 ? 1 : 0;
}
