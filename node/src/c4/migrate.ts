// `la-arch-migrate`: merge the legacy `architecture/model/*.c4` model into `architecture/model.c4` and convert the
// retired `arc42` key format, verified and all-or-nothing.
import { randomUUID } from 'node:crypto';
import {
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
import { basename, dirname, isAbsolute, join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { YAMLError, byCodePoint, decodeUtf8OrNull, loadYaml, message, splitLinesKeepEnds } from '../contract/index.js';
import {
  ARCH_DIR,
  type FileScan,
  RETIRED_ARC42_KEY,
  classify,
  elementDoc,
  isFlatDoc,
  legacyModelDir,
  modelFile,
  stripWhitespace,
  viewsFile,
} from './layout.js';
import { type ModelParse, parseModelFiles, parseModelTexts } from './model.js';
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

/** What one run stages: new text per written path (in report order), doc moves, index renames. */
interface Plan {
  outputs: Map<string, string>;
  created: Set<string>;
  moves: Move[];
  renames: Map<string, string>;
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

/** `text` without each `arc42` line (and each metadata block it empties), and the element doc moves. */
function stripArc42(text: string, model: ModelParse): [string, Move[]] {
  const drop = new Set<number>();
  const moves: Move[] = [];
  const range = ([first, last]: [number, number]): void => {
    for (let i = first; i <= last; i += 1) drop.add(i);
  };
  for (const element of model.elements) {
    if (!hasKey(element.metadata)) continue;
    const span = model.spans.get(element.id);
    if (span === undefined) continue;
    range(span.keys.get(RETIRED_ARC42_KEY) ?? [0, -1]);
    if (Object.keys(element.metadata).length === 1) range(span.block);
    const source = element.metadata[RETIRED_ARC42_KEY];
    if (typeof source === 'string' && source !== elementDoc(element.id)) moves.push({ source, target: elementDoc(element.id) });
  }
  return [
    splitLinesKeepEnds(text)
      .filter((_, i) => !drop.has(i))
      .join(''),
    moves,
  ];
}

function flattened(entries: string[]): Move[] {
  return entries
    .filter((e) => !isFlatDoc(e))
    .map((e) => ({ source: e, target: `${ARCH_DIR}${e.slice(e.lastIndexOf('/') + 1)}` }))
    .filter((m) => m.target !== m.source);
}

/** `rel` is a relative path that stays inside the repo. */
const contained = (rel: string): boolean => rel !== '' && !isAbsolute(rel) && !rel.split('/').includes('..');

/** The first refused move's message, in plan order and check order. */
function refusal(root: string, moves: Move[], keys: unknown[]): string | null {
  const targetsOf = new Map<string, string>();
  const sourcesOf = new Map<string, string>();
  for (const { source, target } of moves) {
    if (!contained(source) || !isFile(join(root, source))) return message('arch-migrate.source-missing', { source });
    const first = targetsOf.get(source);
    if (first !== undefined) return message('arch-migrate.source-moved-twice', { source, first, second: target });
    const other = sourcesOf.get(target);
    if (other !== undefined) return message('arch-migrate.shared-target', { first: other, second: source, target });
    if (lexists(join(root, target))) return message('arch-migrate.target-taken', { source, target });
    if (keys.includes(target)) return message('arch-migrate.diagrams-key-taken', { source, target });
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

const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** `text` with every scalar token equal to a rename source, outside comments, replaced by its target. */
function renamedIndex(text: string, renames: Map<string, string>): string {
  const patterns = [...renames].map(
    ([source, target]) => [new RegExp(`(?<![^\\s\\[{,'"])${escapeRegExp(source)}(?![^\\s\\]},:'"])`, 'gu'), target] as const,
  );
  return splitLinesKeepEnds(text)
    .map((line) => {
      const body = line.replace(/[\r\n]+$/, '');
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

/** Filesystem changes with an undo log; `rollback` restores every touched path byte-for-byte. */
class Commit {
  private readonly undo: (() => void)[] = [];

  create(path: string, text: string): void {
    this.undo.push(() => unlinkSync(path));
    try {
      writeFileSync(path, text, { encoding: 'utf8', flag: 'wx' });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST') this.undo.pop();
      throw error;
    }
  }

  replace(path: string, text: string): void {
    const original = readFileSync(path);
    const temp = join(dirname(path), `.${basename(path)}.${randomUUID().replaceAll('-', '')}.tmp`);
    this.create(temp, text);
    renameSync(temp, path);
    this.undo.push(() => writeFileSync(path, original));
  }

  move(source: string, target: string): void {
    renameSync(source, target);
    this.undo.push(() => renameSync(target, source));
  }

  delete(path: string): void {
    const original = readFileSync(path);
    unlinkSync(path);
    this.undo.push(() => writeFileSync(path, original));
  }

  rmdir(path: string): void {
    rmdirSync(path);
    this.undo.push(() => mkdirSync(path));
  }

  rollback(): void {
    for (const undo of this.undo.toReversed()) {
      try {
        undo();
      } catch {
        // best-effort undo
      }
    }
  }
}

/** Write the outputs, move the docs, delete the legacy files and an emptied model dir; undo it all on an error. */
function write(root: string, plan: Plan, legacy: string[]): string[] {
  const commit = new Commit();
  const modelDir = join(root, legacyModelDir());
  let removedDir = false;
  try {
    for (const [rel, text] of plan.outputs) {
      if (plan.created.has(rel)) commit.create(join(root, rel), text);
      else commit.replace(join(root, rel), text);
    }
    for (const move of plan.moves) commit.move(join(root, move.source), join(root, move.target));
    for (const rel of legacy) commit.delete(join(root, rel));
    if (legacy.length > 0 && readdirSync(modelDir).length === 0) {
      commit.rmdir(modelDir);
      removedDir = true;
    }
  } catch (error) {
    commit.rollback();
    throw error;
  }
  const report = [...plan.outputs.keys()].map((rel) => message('arch-migrate.written', { path: rel }));
  report.push(...plan.moves.map((m) => message('arch-migrate.moved', { source: m.source, target: m.target })));
  report.push(...legacy.map((rel) => message('arch-migrate.deleted', { path: rel })));
  if (removedDir) report.push(message('arch-migrate.deleted', { path: legacyModelDir() }));
  return report;
}

/** Migrate the repo at `root`; the lines to print. Throws (having written nothing) when it cannot. */
export function migrate(root: string): string[] {
  const layout = classify(root);
  if (layout.state !== 'canonical' && layout.state !== 'legacy') throw new MigrateError(layout.message ?? '');
  const legacy = layout.legacyFiles;
  let before: ModelParse;
  let modelText: string;
  if (legacy.length > 0) {
    before = parseModelFiles(legacy.map((rel) => join(root, rel)));
    modelText = mergedModel(legacy.map((rel) => layout.scans.get(rel) as FileScan));
  } else {
    modelText = readExact(join(root, modelFile()));
    before = parseModelTexts([modelText]);
  }
  const index = readIndex(root);
  const entries = crossCutting(index);
  const keyed = before.elements.some((e) => hasKey(e.metadata));
  if (legacy.length === 0 && !keyed && entries.every(isFlatDoc)) return [message('arch-migrate.nothing')];
  const [stripped, elementMoves] = stripArc42(modelText, parseModelTexts([modelText]));
  const entryMoves = flattened(entries);
  const moves = [...elementMoves, ...entryMoves];
  const keys = diagramKeys(index);
  const refused = refusal(root, moves, keys);
  if (refused !== null) throw new MigrateError(refused);
  const renamed = new Set<unknown>([...entryMoves.map((m) => m.source), ...keys]);
  const renames = new Map(moves.filter((m) => renamed.has(m.source)).map((m) => [m.source, m.target]));
  const outputs = new Map<string, string>();
  const created = new Set<string>();
  if (legacy.length > 0 || stripped !== modelText) outputs.set(modelFile(), stripped);
  if (legacy.length > 0) {
    created.add(modelFile());
    if (!layout.viewsExists) {
      outputs.set(viewsFile(), EMPTY_VIEWS);
      created.add(viewsFile());
    }
  }
  if (renames.size > 0 && index.text !== null) outputs.set(INDEX_REL, renamedIndex(index.text, renames));
  const plan: Plan = { outputs, created, moves, renames };
  verify(root, before, plan, index, new Set(entryMoves.map((m) => m.source)));
  return write(root, plan, legacy);
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
