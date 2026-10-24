// `la-arch-migrate`: convert the repo to the current format: merge a legacy model layout, convert the retired `arc42`
// key format and stamp `format`, verified and all-or-nothing.
import { randomBytes } from 'node:crypto';
import {
  chmodSync,
  existsSync,
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
  currentFormat,
  formatProblem,
  isVersion,
  readCommitted,
  stampFormat,
} from '../config/index.js';
import {
  YAMLError,
  byCodePoint,
  configFile,
  decodeUtf8OrNull,
  loadYaml,
  message,
  splitLines,
  splitLinesKeepEnds,
} from '../contract/index.js';
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

const INDEX_REL = 'architecture/index.yaml';

/** The repo cannot be migrated; nothing was written. */
export class MigrateError extends Error {}

interface Move {
  source: string;
  target: string;
}

/** `architecture/index.yaml` as text and as data; `data` is null when it is absent or not a mapping. */
interface Index {
  text: string | null;
  data: Map<unknown, unknown> | null;
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

function readIndex(root: string): Index {
  const path = join(root, INDEX_REL);
  if (!isFile(path)) return { text: null, data: null };
  const text = decodeUtf8OrNull(readFileSync(path));
  if (text === null) return { text: null, data: null };
  let data: unknown = null;
  try {
    data = loadYaml(text);
  } catch (error) {
    if (!(error instanceof YAMLError)) throw error;
  }
  return { text, data: data instanceof Map ? data : null };
}

function crossCutting(index: Index): string[] {
  const entries = index.data?.get('cross_cutting_arc42');
  return Array.isArray(entries) ? entries.filter((e): e is string => typeof e === 'string') : [];
}

function diagramKeys(index: Index): unknown[] {
  const diagrams = index.data?.get('diagrams');
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
function verify(root: string, before: ModelParse, plan: Plan, index: Index, movedEntries: Set<string>): void {
  const expected = [comparable(withoutArc42(before)), parseViews(root, before)];
  const stagedIndex = plan.outputs.get(INDEX_REL) ?? index.text;
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
function indexAsExpected(plan: Plan, index: Index, movedEntries: Set<string>): boolean {
  const written = plan.outputs.get(INDEX_REL);
  if (written === undefined || index.data === null) return true;
  return isDeepStrictEqual(loadYaml(written), expectedIndex(index.data, plan.renames, movedEntries));
}

/** One applied change: the path it touched, how to undo it, and whether the path is back as it was. */
interface Step {
  rel: string;
  undo: () => void;
  restored: () => boolean;
}

/** Create `rel` exclusively, journalled before the open so a half-made file is undone too. */
function createExclusive(root: string, rel: string, text: string, steps: Step[]): void {
  const path = join(root, rel);
  steps.push({ rel, undo: () => rmSync(path, { force: true }), restored: () => !lexists(path) });
  try {
    writeFileSync(path, text, { encoding: 'utf8', flag: 'wx' });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') steps.pop();
    throw error;
  }
}

const modeOf = (path: string): number => statSync(path).mode & 0o7777;

function remove(root: string, rel: string, original: Buffer, steps: Step[]): void {
  const path = join(root, rel);
  const mode = modeOf(path);
  unlinkSync(path);
  steps.push({
    rel,
    undo: () => {
      writeFileSync(path, original);
      chmodSync(path, mode);
    },
    restored: () => isFile(path) && modeOf(path) === mode && readFileSync(path).equals(original),
  });
}

function removeDir(root: string, rel: string, steps: Step[]): void {
  const path = join(root, rel);
  const mode = modeOf(path);
  rmdirSync(path);
  steps.push({
    rel,
    undo: () => {
      mkdirSync(path);
      chmodSync(path, mode);
    },
    restored: () => existsSync(path) && statSync(path).isDirectory() && modeOf(path) === mode,
  });
}

/** Replace `rel` with `text` through a sibling temp file and an atomic rename, keeping its mode. */
function swapIn(root: string, rel: string, text: string, steps: Step[]): void {
  const path = join(root, rel);
  const temp = posix.join(posix.dirname(rel), `.${basename(rel)}.${randomBytes(4).toString('hex')}.tmp`);
  createExclusive(root, temp, text, steps);
  chmodSync(join(root, temp), modeOf(path));
  renameSync(join(root, temp), path);
}

/** Replace `rel`, journalled so a rollback puts its bytes and mode back. */
function replace(root: string, rel: string, text: string, steps: Step[]): void {
  const path = join(root, rel);
  const original = readFileSync(path);
  const mode = modeOf(path);
  swapIn(root, rel, text, steps);
  steps.push({
    rel,
    undo: () => {
      writeFileSync(path, original);
      chmodSync(path, mode);
    },
    restored: () => isFile(path) && modeOf(path) === mode && readFileSync(path).equals(original),
  });
}

function move(root: string, step: Move, steps: Step[]): void {
  const [source, target] = [join(root, step.source), join(root, step.target)];
  renameSync(source, target);
  steps.push({ rel: step.source, undo: () => renameSync(target, source), restored: () => isFile(source) && !lexists(target) });
}

/** Undo `steps` in reverse; an error naming every path that could not be put back, null when all were. */
function rollback(steps: Step[], error: Error): MigrateError | null {
  for (const step of steps.toReversed()) {
    try {
      step.undo();
    } catch {
      // judged by `restored` below
    }
  }
  const left = [...new Set(steps.filter((step) => !step.restored()).map((step) => step.rel))].sort(byCodePoint);
  if (left.length === 0) return null;
  return new MigrateError(message('arch-migrate.rollback-failed', { error: error.message, paths: left.join(', ') }));
}

/** Write the layout files, move the docs, delete the legacy files and an emptied model dir, replace the config last; all or nothing. */
function write(root: string, plan: Plan, stamped: string): string[] {
  const steps: Step[] = [];
  const deleted: string[] = [];
  const modelDir = legacyModelDir();
  try {
    for (const [rel, text] of plan.outputs) {
      if (plan.created.has(rel)) createExclusive(root, rel, text, steps);
      else replace(root, rel, text, steps);
    }
    for (const m of plan.moves) move(root, m, steps);
    for (const [rel, original] of plan.legacy) {
      remove(root, rel, original, steps);
      deleted.push(rel);
    }
    if (plan.legacy.size > 0 && readdirSync(join(root, modelDir)).length === 0) {
      removeDir(root, modelDir, steps);
      deleted.push(modelDir);
    }
    swapIn(root, configFile(), stamped, steps);
  } catch (error) {
    throw rollback(steps, error as Error) ?? error;
  }
  return [
    ...[...plan.outputs.keys(), configFile()].map((rel) => message('arch-migrate.written', { path: rel })),
    ...plan.moves.map((m) => message('arch-migrate.moved', { source: m.source, target: m.target })),
    ...deleted.map((rel) => message('arch-migrate.deleted', { path: rel })),
  ];
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
  if (renames.size > 0 && index.text !== null) outputs.set(INDEX_REL, renamedIndex(index.text, renames));
  const plan: Plan = { outputs, created, moves, renames, legacy };
  verify(root, before, plan, index, new Set(entryMoves.map((m) => m.source)));
  return plan;
}

/** The stamped config text, or null when the repo already declares the current format. */
function stamped(root: string): string | null {
  let committed;
  try {
    committed = readCommitted(root);
  } catch (error) {
    if (error instanceof ConfigError) throw new MigrateError(error.message);
    throw error;
  }
  if (committed === null) throw new MigrateError(message('arch-migrate.no-config'));
  const current = currentFormat();
  const data = committed.data ?? new Map<unknown, unknown>();
  if (data.has(FORMAT_KEY)) {
    const problem = formatProblem(data);
    const declared = data.get(FORMAT_KEY);
    if (problem !== null && isVersion(declared) && compareVersions(declared, current) < 0) {
      throw new MigrateError(message('arch-migrate.unknown-format', { declared, current }));
    }
    if (problem !== null) throw new MigrateError(problem);
    return null;
  }
  const text = stampFormat(committed.text);
  if (text === null) throw new MigrateError(message('arch-migrate.stamp-mismatch', { current }));
  return text;
}

/** Migrate the repo at `root`; the lines to print. Throws having changed nothing, unless the error names the paths. */
export function migrate(root: string): string[] {
  const text = stamped(root);
  if (text === null) return [message('arch-migrate.nothing', { current: currentFormat() })];
  return write(root, planOf(root), text);
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
