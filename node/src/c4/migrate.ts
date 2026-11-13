// `la-arch-migrate`: convert the repo to the current format one released format at a time and stamp `format`,
// verified and all-or-nothing.
import { randomBytes } from 'node:crypto';
import {
  chmodSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  rmdirSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, isAbsolute, join, posix } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import {
  ConfigError,
  FORMAT_KEY,
  compareVersions,
  formatProblem,
  isVersion,
  readCommitted,
  releasedFormats,
  stampFormat,
} from '../config/index.js';
import {
  byCodePoint,
  configFile,
  loadYaml,
  message,
  splitLines,
  splitLinesKeepEnds,
} from '../contract/index.js';
import { INDEX_REL, type Index, loadIndex } from './index-file.js';
import {
  ARCH_DIR,
  type FileScan,
  RETIRED_ARC42_KEY,
  classify,
  elementDoc,
  isFlatDoc,
  leadingWhitespace,
  legacyModelDir,
  modelFile,
  sources,
  stripWhitespace,
  trailingWhitespace,
  viewsFile,
} from './layout.js';
import { type ModelParse, type Pos, parseModelFiles, parseModelTexts, stripLineComment } from './model.js';
import { EMPTY_VIEWS, parseViews } from './views.js';

/** The repo cannot be migrated; nothing was written. */
export class MigrateError extends Error {}

interface Move {
  source: string;
  target: string;
}

/** What one run stages: new text per written path (in report order), doc moves, index renames, legacy files. */
interface Plan {
  outputs: Map<string, string>;
  created: Set<string>;
  moves: Move[];
  renames: Map<string, string>;
  legacy: Map<string, Buffer>;
}

/** The comment and blank lines outside every block; a comment sharing a line with a block keeps its own line. */
function outsideLines(fileScan: FileScan): string {
  const { text } = fileScan;
  let outside = '';
  let pos = 0;
  for (const block of fileScan.blocks) {
    outside += `${text.slice(pos, block.start)}\0`;
    pos = (block.close ?? text.length) + 1;
  }
  outside += text.slice(pos);
  const lines = outside.split('\n');
  if (lines.at(-1) === '') lines.pop();
  let kept = '';
  for (const line of lines) {
    if (!line.includes('\0')) kept += `${line}\n`;
    else {
      const comment = stripWhitespace(line.replaceAll('\0', ''));
      if (comment) kept += `${comment}\n`;
    }
  }
  return kept;
}

/** The interior of every `kind` block, in file then block order; an empty block when there is none. */
function interiors(scans: FileScan[], kind: string): string {
  const parts = scans.flatMap((s) => s.blocks.filter((b) => b.kind === kind).map((b) => s.text.slice(b.open + 1, b.close ?? undefined)));
  return parts.length > 0 ? parts.join('') : '\n';
}

/** The canonical `model.c4` text for the legacy files' scans, in sorted-file order. */
export function mergedModel(scans: FileScan[]): string {
  const head = scans.map(outsideLines).join('');
  return `${head}specification {${interiors(scans, 'specification')}}\nmodel {${interiors(scans, 'model')}}\n`;
}

const readExact = (path: string): string => readFileSync(path).toString('utf8');

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function lexists(path: string): boolean {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
}

/** The index, null when absent; MigrateError when it is unusable. */
function readIndex(root: string): Index | null {
  const index = loadIndex(root);
  if (typeof index === 'string') throw new MigrateError(index);
  return index;
}

/** The index's `cross_cutting_arc42` paths; empty without an index or that list. */
function crossCutting(index: Index | null): string[] {
  const entries = index?.data.get('cross_cutting_arc42');
  return Array.isArray(entries) ? entries.filter((e): e is string => typeof e === 'string') : [];
}

/** The keys of the index's `diagrams` mapping; empty without an index or that mapping. */
function diagramKeys(index: Index | null): unknown[] {
  const diagrams = index?.data.get('diagrams');
  return diagrams instanceof Map ? [...diagrams.keys()] : [];
}

const hasKey = (metadata: object): boolean => Object.hasOwn(metadata, RETIRED_ARC42_KEY);

/**
 * `text` without each `arc42` statement (or the metadata block it alone fills), and the element doc moves,
 * a doc already at its target included.
 */
function stripArc42(text: string, model: ModelParse): [string, Move[]] {
  const cuts: [Pos, Pos][] = [];
  const moves: Move[] = [];
  for (const element of model.elements) {
    if (!hasKey(element.metadata)) continue;
    const span = model.spans.get(element.id);
    const keySpan = span?.keys.get(RETIRED_ARC42_KEY);
    if (span === undefined || keySpan === undefined) continue;
    cuts.push(Object.keys(element.metadata).length === 1 ? span.block : keySpan);
    const source = element.metadata[RETIRED_ARC42_KEY];
    if (typeof source === 'string') moves.push({ source, target: elementDoc(element.id) });
  }
  return [cut(text, cuts), moves];
}

/** `text` without each span: with its lines when nothing else is on them, else with the whitespace on one side. */
function cut(text: string, spans: [Pos, Pos][]): string {
  const lines = splitLinesKeepEnds(text);
  const starts = [0];
  for (const line of lines) starts.push((starts.at(-1) ?? 0) + line.length);
  const ranges = spans.map((span) => cutRange(text, lines, starts, span)).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let out = '';
  let pos = 0;
  for (const [start, end] of ranges) {
    out += text.slice(pos, Math.max(pos, start));
    pos = Math.max(pos, end);
  }
  return out + text.slice(pos);
}

function cutRange(text: string, lines: string[], starts: number[], [[first, firstCol], [last, lastCol]]: [Pos, Pos]): [number, number] {
  const lineStart = starts[first] ?? 0;
  const lastStart = starts[last] ?? 0;
  const [start, end] = [lineStart + firstCol, lastStart + lastCol];
  const before = text.slice(lineStart, start);
  const after = text.slice(end, lastStart + (splitLines(lines[last] ?? '')[0] ?? '').length);
  const blank = (part: string): boolean => stripWhitespace(part) === '';
  if (blank(before) && blank(stripLineComment(after))) return [lineStart, starts[last + 1] ?? text.length];
  if (blank(before)) return [start, end + leadingWhitespace(after)];
  return [start - trailingWhitespace(before), end];
}

function flattened(entries: string[]): Move[] {
  return entries
    .filter((e) => !isFlatDoc(e))
    .map((e) => ({ source: e, target: `${ARCH_DIR}${e.slice(e.lastIndexOf('/') + 1)}` }))
    .filter((m) => m.target !== m.source);
}

/** `rel` is a relative path that stays inside the repo. */
const contained = (rel: string): boolean => rel !== '' && !isAbsolute(rel) && !rel.split('/').includes('..');

/** The first refused move's message, in plan order and check order; a doc already at its target claims its path. */
function refusal(root: string, moves: Move[], keys: unknown[]): string | null {
  const targetsOf = new Map<string, string>();
  const sourcesOf = new Map<string, string>();
  for (const { source, target } of moves) {
    if (!contained(source) || !isFile(join(root, source))) return message('arch-migrate.source-missing', { source });
    const first = targetsOf.get(source);
    if (first !== undefined) return message('arch-migrate.source-moved-twice', { source, first, second: target });
    const other = sourcesOf.get(target);
    if (other !== undefined) return message('arch-migrate.shared-target', { first: other, second: source, target });
    if (source !== target && lexists(join(root, target))) return message('arch-migrate.target-taken', { source, target });
    if (source !== target && keys.includes(target)) return message('arch-migrate.diagrams-key-taken', { source, target });
    targetsOf.set(source, target);
    sourcesOf.set(target, source);
  }
  return null;
}

/** Where a YAML line's comment starts (outside quotes, after whitespace or at the start), else its length. */
function codeEnd(line: string): number {
  let quote = '';
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i] ?? '';
    if (quote) {
      if (ch === quote) quote = '';
    } else if (ch === "'" || ch === '"') quote = ch;
    else if (ch === '#' && (i === 0 || ' \t'.includes(line[i - 1] ?? ''))) return i;
  }
  return line.length;
}

const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);

/** `line` without its trailing `\r` and `\n` characters. */
function withoutLineBreak(line: string): string {
  let end = line.length;
  while (end > 0 && (line[end - 1] === '\n' || line[end - 1] === '\r')) end -= 1;
  return line.slice(0, end);
}

/** `text` with every scalar token equal to a rename source, outside comments, replaced by its target. */
function renamedIndex(text: string, renames: Map<string, string>): string {
  const patterns = [...renames].map(
    ([source, target]) => [new RegExp(String.raw`(?<![^\s\[{,'"])${escapeRegExp(source)}(?![^\s\]},:'"])`, 'gu'), target] as const,
  );
  return splitLinesKeepEnds(text)
    .map((line) => {
      const body = withoutLineBreak(line);
      const end = codeEnd(body);
      let code = body.slice(0, end);
      for (const [pattern, target] of patterns) code = code.replace(pattern, () => target);
      return code + line.slice(end);
    })
    .join('');
}

/** `data` with the moved cross-cutting entries and the moved diagrams keys renamed. */
function expectedIndex(data: Map<unknown, unknown>, renames: Map<string, string>, movedEntries: Set<string>): Map<unknown, unknown> {
  const expected = new Map(data);
  const entries = data.get('cross_cutting_arc42');
  if (Array.isArray(entries)) {
    expected.set(
      'cross_cutting_arc42',
      entries.map((e) => (typeof e === 'string' && movedEntries.has(e) ? renames.get(e) : e)),
    );
  }
  const diagrams = data.get('diagrams');
  if (diagrams instanceof Map) {
    expected.set('diagrams', new Map([...diagrams].map(([k, v]) => [typeof k === 'string' ? (renames.get(k) ?? k) : k, v])));
  }
  return expected;
}

/** `model` without line spans, its findings as sorted multisets (merging spec blocks may reorder them). */
function comparable(model: ModelParse): unknown {
  return {
    elements: model.elements,
    relations: model.relations,
    findings: model.findings.toSorted(byCodePoint),
    metadataFindings: model.metadataFindings.toSorted(byCodePoint),
  };
}

/** `model` as it reads once every `arc42` key, and every metadata block left empty, is gone. */
function withoutArc42(model: ModelParse): ModelParse {
  const elements = model.elements.map((element) => {
    if (!hasKey(element.metadata)) return element;
    const metadata = Object.fromEntries(Object.entries(element.metadata).filter(([key]) => key !== RETIRED_ARC42_KEY));
    return { ...element, metadata, hasMetadata: Object.keys(metadata).length > 0 };
  });
  return { ...model, elements };
}

/**
 * MigrateError unless the staged result parses like the input, apart from the converted arc42 format.
 * A doc moves by rename, so it stays byte-identical by construction.
 */
function verify(root: string, before: ModelParse, plan: Plan, index: Index | null, movedEntries: Set<string>): void {
  const expected = [comparable(withoutArc42(before)), parseViews(root, before)];
  const stagedIndex = plan.outputs.get(INDEX_REL) ?? index?.text ?? null;
  const staging = mkdtempSync(join(tmpdir(), 'la-arch-migrate-'));
  let after: unknown[];
  try {
    mkdirSync(join(staging, 'architecture'));
    if (stagedIndex !== null) writeFileSync(join(staging, INDEX_REL), stagedIndex, 'utf8');
    const views = plan.outputs.get(viewsFile());
    if (views !== undefined) writeFileSync(join(staging, viewsFile()), views, 'utf8');
    else if (isFile(join(root, viewsFile()))) writeFileSync(join(staging, viewsFile()), readFileSync(join(root, viewsFile())));
    const modelText = plan.outputs.get(modelFile()) ?? readExact(join(root, modelFile()));
    const stagedModel = parseModelTexts([modelText]);
    after = [comparable(stagedModel), parseViews(staging, stagedModel)];
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
  if (!isDeepStrictEqual(expected, after) || !indexAsExpected(plan, index, movedEntries)) {
    throw new MigrateError(message('arch-migrate.mismatch'));
  }
}

/** The staged index parses to the input's, with only the planned renames. */
function indexAsExpected(plan: Plan, index: Index | null, movedEntries: Set<string>): boolean {
  const written = plan.outputs.get(INDEX_REL);
  if (written === undefined || index === null) return true;
  return isDeepStrictEqual(loadYaml(written), expectedIndex(index.data, plan.renames, movedEntries));
}

/** A path's state: a file's bytes and mode, a directory's mode, or absent. */
interface PathState {
  data: Buffer | null;
  mode: number | null;
  isDir: boolean;
}

const ABSENT: PathState = { data: null, mode: null, isDir: false };
const modeOf = (path: string): number => statSync(path).mode & 0o7777;

function stateOf(path: string): PathState {
  if (!lexists(path)) return ABSENT;
  if (lstatSync(path).isDirectory()) return { data: null, mode: modeOf(path), isDir: true };
  return { data: readFileSync(path), mode: modeOf(path), isDir: false };
}

const sameState = (a: PathState, b: PathState): boolean =>
  a.isDir === b.isDir && a.mode === b.mode && (a.data === null ? b.data === null : b.data !== null && a.data.equals(b.data));

/** Put a file or directory back with its bytes and mode. */
function restore(path: string, state: PathState): void {
  if (state.isDir) mkdirSync(path);
  else writeFileSync(path, state.data ?? Buffer.alloc(0));
  if (state.mode !== null) chmodSync(path, state.mode);
}

/** The file at a path: its path before the run (null when the run created it) and whether the run wrote it. */
interface Held {
  origin: string | null;
  written: boolean;
}

/** The filesystem changes of one run, all undone on any failure, and their net effect. */
export class Transaction {
  readonly root: string;
  private readonly undos: (() => void)[] = [];
  private readonly first = new Map<string, PathState>();
  private readonly held = new Map<string, Held | null>();
  private readonly written: string[] = [];
  private readonly moved: string[] = [];
  private readonly vacated: string[] = [];

  constructor(root: string) {
    this.root = root;
  }

  private touch(rel: string): string {
    const path = join(this.root, rel);
    if (!this.first.has(rel)) this.first.set(rel, stateOf(path));
    return path;
  }

  private holder(rel: string): Held | null {
    if (this.held.has(rel)) return this.held.get(rel) ?? null;
    return lexists(join(this.root, rel)) ? { origin: rel, written: false } : null;
  }

  private wrote(rel: string, held: Held | null): void {
    this.held.set(rel, { origin: held?.origin ?? null, written: true });
    if (!this.written.includes(rel)) this.written.push(rel);
  }

  /** Create `rel` exclusively, journalled before the open so a half-made file is undone too. */
  private createExclusive(rel: string, text: string): void {
    const path = this.touch(rel);
    this.undos.push(() => rmSync(path, { force: true }));
    try {
      writeFileSync(path, text, { encoding: 'utf8', flag: 'wx' });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST') this.undos.pop();
      throw error;
    }
  }

  /** Create the new file `rel`. */
  create(rel: string, text: string): void {
    const held = this.holder(rel);
    this.createExclusive(rel, text);
    this.wrote(rel, held);
  }

  /** Replace `rel` through a sibling temp file and an atomic rename, keeping its mode. */
  replace(rel: string, text: string): void {
    const held = this.holder(rel);
    const path = this.touch(rel);
    const original = stateOf(path);
    const temp = posix.join(posix.dirname(rel), `.${basename(rel)}.${randomBytes(4).toString('hex')}.tmp`);
    this.createExclusive(temp, text);
    chmodSync(join(this.root, temp), modeOf(path));
    renameSync(join(this.root, temp), path);
    this.undos.push(() => restore(path, original));
    this.wrote(rel, held);
  }

  /** Move the file `source` to the free path `target`. */
  move(source: string, target: string): void {
    const held = this.holder(source);
    const [sourcePath, targetPath] = [this.touch(source), this.touch(target)];
    renameSync(sourcePath, targetPath);
    this.undos.push(() => renameSync(targetPath, sourcePath));
    this.held.set(source, null);
    this.held.set(target, held);
    if (held?.origin != null && !this.moved.includes(held.origin)) this.moved.push(held.origin);
    if (held?.written && !this.written.includes(target)) this.written.push(target);
    this.vacated.push(source);
  }

  /** Delete the file `rel`. */
  delete(rel: string): void {
    const path = this.touch(rel);
    const original = stateOf(path);
    unlinkSync(path);
    this.vacate(rel, () => restore(path, original));
  }

  /** Remove the empty directory `rel`. */
  removeDir(rel: string): void {
    const path = this.touch(rel);
    const original = stateOf(path);
    rmdirSync(path);
    this.vacate(rel, () => restore(path, original));
  }

  private vacate(rel: string, undo: () => void): void {
    this.undos.push(undo);
    this.held.set(rel, null);
    this.vacated.push(rel);
  }

  /** Undo every change in reverse; an error naming every path left changed, null when all were put back. */
  rollback(error: Error): MigrateError | null {
    for (const undo of this.undos.toReversed()) {
      try {
        undo();
      } catch {
        // judged against the first-touch states below
      }
    }
    const left = [...this.first]
      .filter(([rel, state]) => !sameState(stateOf(join(this.root, rel)), state))
      .map(([rel]) => rel)
      .sort(byCodePoint);
    if (left.length === 0) return null;
    return new MigrateError(message('arch-migrate.rollback-failed', { error: error.message, paths: left.join(', ') }));
  }

  /** The net effect: written paths (`last` last), then composed moves, then deleted paths. */
  report(last: string): string[] {
    const exists = (rel: string): boolean => lexists(join(this.root, rel));
    const written = this.written.filter(exists);
    const ordered = [...written.filter((rel) => rel !== last), ...written.filter((rel) => rel === last)];
    const final = new Map<string, string>();
    for (const [rel, held] of this.held) if (held?.origin != null) final.set(held.origin, rel);
    const moves = this.moved.filter((origin) => (final.get(origin) ?? origin) !== origin).map((origin) => [origin, final.get(origin) as string]);
    const movedFrom = new Set(moves.map(([origin]) => origin));
    const deleted: string[] = [];
    for (const rel of this.vacated) {
      const before = this.first.get(rel) ?? ABSENT;
      if (!sameState(before, ABSENT) && !exists(rel) && !movedFrom.has(rel) && !deleted.includes(rel)) deleted.push(rel);
    }
    return [
      ...ordered.map((rel) => message('arch-migrate.written', { path: rel })),
      ...moves.map(([source, target]) => message('arch-migrate.moved', { source, target })),
      ...deleted.map((rel) => message('arch-migrate.deleted', { path: rel })),
    ];
  }
}

/** Write the layout files, move the docs, delete the legacy files and an emptied model dir. */
function apply(plan: Plan, tx: Transaction): void {
  for (const [rel, text] of plan.outputs) {
    if (plan.created.has(rel)) tx.create(rel, text);
    else tx.replace(rel, text);
  }
  for (const m of plan.moves) tx.move(m.source, m.target);
  for (const rel of plan.legacy.keys()) tx.delete(rel);
  const modelDir = legacyModelDir();
  if (plan.legacy.size > 0 && readdirSync(join(tx.root, modelDir)).length === 0) tx.removeDir(modelDir);
}

const NO_PLAN = (): Plan => ({ outputs: new Map(), created: new Set(), moves: [], renames: new Map(), legacy: new Map() });

/** The layout and arc42 conversions to apply; none when there is no model to convert. */
function planOf(root: string): Plan {
  if (sources(root).length === 0) return NO_PLAN();
  const layout = classify(root);
  if (layout.state !== 'canonical' && layout.state !== 'legacy') throw new MigrateError(layout.message ?? '');
  const legacy = new Map(layout.legacyFiles.map((rel) => [rel, readFileSync(join(root, rel))]));
  let before: ModelParse;
  let modelText: string;
  if (legacy.size > 0) {
    before = parseModelFiles(layout.legacyFiles.map((rel) => join(root, rel)));
    modelText = mergedModel(layout.legacyFiles.map((rel) => layout.scans.get(rel) as FileScan));
  } else {
    modelText = readExact(join(root, modelFile()));
    before = parseModelTexts([modelText]);
  }
  const index = readIndex(root);
  const [stripped, elementMoves] = stripArc42(modelText, parseModelTexts([modelText]));
  const entryMoves = flattened(crossCutting(index));
  const keys = diagramKeys(index);
  const refused = refusal(root, [...elementMoves, ...entryMoves], keys);
  if (refused !== null) throw new MigrateError(refused);
  const moves = [...elementMoves, ...entryMoves].filter((m) => m.source !== m.target);
  const renamed = new Set<unknown>([...entryMoves.map((m) => m.source), ...keys]);
  const renames = new Map(moves.filter((m) => renamed.has(m.source)).map((m) => [m.source, m.target]));
  const outputs = new Map<string, string>();
  const created = new Set<string>();
  if (legacy.size > 0 || stripped !== modelText) outputs.set(modelFile(), stripped);
  if (legacy.size > 0) {
    created.add(modelFile());
    if (!layout.viewsExists) {
      outputs.set(viewsFile(), EMPTY_VIEWS);
      created.add(viewsFile());
    }
  }
  if (renames.size > 0 && index !== null) outputs.set(INDEX_REL, renamedIndex(index.text, renames));
  const plan: Plan = { outputs, created, moves, renames, legacy };
  verify(root, before, plan, index, new Set(entryMoves.map((m) => m.source)));
  return plan;
}

/** One conversion: from the `source` format (null: a repo that declares none) to the `target` format. */
export interface MigrationStep {
  source: string | null;
  target: string;
  apply: (root: string, tx: Transaction) => void;
}

export const STEPS: MigrationStep[] = [{ source: null, target: '0.4.0', apply: (root, tx) => apply(planOf(root), tx) }];

/** The declared format (null when absent) and the config text; null when it is current; MigrateError when it cannot be migrated. */
function declaredFormat(root: string, formats: string[]): [string | null, string] | null {
  let committed;
  try {
    committed = readCommitted(root);
  } catch (error) {
    if (error instanceof ConfigError) throw new MigrateError(error.message);
    throw error;
  }
  if (committed === null) throw new MigrateError(message('arch-migrate.no-config'));
  const data = committed.data ?? new Map<unknown, unknown>();
  if (!data.has(FORMAT_KEY)) return [null, committed.text];
  const current = formats.at(-1) as string;
  const declared = data.get(FORMAT_KEY);
  const problem = formatProblem(data, current);
  if (problem === null) return null;
  if (!isVersion(declared) || compareVersions(declared, current) > 0) throw new MigrateError(problem);
  if (!formats.includes(declared)) throw new MigrateError(message('arch-migrate.unknown-format', { declared, current }));
  return [declared, committed.text];
}

/**
 * Migrate the repo at `root` through `steps` (default: STEPS) up to the last of `formats` (default: the released
 * ones); the lines to print. Throws having changed nothing, unless the error names the paths.
 */
export function migrate(root: string, { steps = STEPS, formats = releasedFormats() }: { steps?: MigrationStep[]; formats?: string[] } = {}): string[] {
  const current = formats.at(-1) as string;
  const found = declaredFormat(root, formats);
  if (found === null) return [message('arch-migrate.nothing', { current })];
  const [declared, text] = found;
  const stamped = stampFormat(text, current);
  if (stamped === null) throw new MigrateError(message('arch-migrate.stamp-mismatch', { current }));
  const bySource = new Map(steps.map((step) => [step.source, step]));
  const sources = declared === null ? [null, ...formats.slice(0, -1)] : formats.slice(formats.indexOf(declared), -1);
  const tx = new Transaction(root);
  try {
    for (const source of sources) (bySource.get(source) as MigrationStep).apply(root, tx);
    tx.replace(configFile(), stamped);
  } catch (error) {
    throw tx.rollback(error as Error) ?? error;
  }
  return tx.report(configFile());
}

/** `la-arch-migrate`: print each written, moved and deleted path, or exit 2 having changed nothing. */
export function run(root: string): number {
  let report: string[];
  try {
    report = migrate(root);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException)?.code;
    if (!(error instanceof MigrateError) && !(typeof code === 'string' && code.startsWith('E'))) throw error;
    process.stderr.write(`${message('arch-migrate.error', { error: (error as Error).message })}\n`);
    return 2;
  }
  for (const line of report) process.stdout.write(`${line}\n`);
  return 0;
}
