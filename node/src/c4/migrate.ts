// `la-arch-migrate`: convert the repo to the current format, merging a legacy model layout and stamping `format`.
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
import { join } from 'node:path';
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
import { byCodePoint, configFile, message } from '../contract/index.js';
import { type FileScan, classify, legacyModelDir, modelFile, sources, stripWhitespace, viewsFile } from './layout.js';
import { type ModelParse, parseModel, parseModelFiles } from './model.js';
import { EMPTY_VIEWS, parseViews } from './views.js';

const INDEX_REL = 'architecture/index.yaml';

/** The repo cannot be migrated; nothing was written. */
export class MigrateError extends Error {}

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

/** `model` with findings as sorted multisets: merging spec blocks may reorder them. */
function normalized(model: ModelParse): ModelParse {
  return { ...model, findings: model.findings.toSorted(byCodePoint), metadataFindings: model.metadataFindings.toSorted(byCodePoint) };
}

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

/** MigrateError unless the staged canonical layout parses exactly like the legacy one. */
function verify(root: string, legacy: string[], outputs: Map<string, string>): void {
  const legacyModel = parseModelFiles(legacy);
  const before = [normalized(legacyModel), parseViews(root, legacyModel)];
  const staging = mkdtempSync(join(tmpdir(), 'la-arch-migrate-'));
  let after: unknown[];
  try {
    mkdirSync(join(staging, 'architecture'));
    for (const rel of [INDEX_REL, viewsFile()]) {
      if (isFile(join(root, rel))) writeFileSync(join(staging, rel), readFileSync(join(root, rel)));
    }
    for (const [rel, text] of outputs) writeFileSync(join(staging, rel), text, 'utf8');
    const stagedModel = parseModel(staging);
    after = [normalized(stagedModel), parseViews(staging, stagedModel)];
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
  if (!isDeepStrictEqual(before, after)) throw new MigrateError(message('arch-migrate.mismatch'));
}

/** One applied change: the path it touched, how to undo it, and whether the path is back as it was. */
interface Step {
  rel: string;
  undo: () => void;
  restored: () => boolean;
}

const lexists = (path: string): boolean => {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
};

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

/** Replace the config with `stamped` through a sibling temp file and an atomic rename. */
function replaceConfig(root: string, stamped: string, steps: Step[]): void {
  const config = join(root, configFile());
  const temp = `.${configFile()}.${randomBytes(4).toString('hex')}.tmp`;
  createExclusive(root, temp, stamped, steps);
  chmodSync(join(root, temp), modeOf(config));
  renameSync(join(root, temp), config);
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

/** Create every output, delete the legacy files and an emptied model dir, replace the config last; all or nothing. */
function write(root: string, outputs: Map<string, string>, legacy: Map<string, Buffer>, stamped: string): string[] {
  const steps: Step[] = [];
  const deleted: string[] = [];
  const modelDir = legacyModelDir();
  try {
    for (const [rel, text] of outputs) createExclusive(root, rel, text, steps);
    for (const [rel, original] of legacy) {
      remove(root, rel, original, steps);
      deleted.push(rel);
    }
    if (legacy.size > 0 && readdirSync(join(root, modelDir)).length === 0) {
      removeDir(root, modelDir, steps);
      deleted.push(modelDir);
    }
    replaceConfig(root, stamped, steps);
  } catch (error) {
    throw rollback(steps, error as Error) ?? error;
  }
  const written = [...outputs.keys(), configFile()];
  return [
    ...written.map((rel) => message('arch-migrate.written', { path: rel })),
    ...deleted.map((rel) => message('arch-migrate.deleted', { path: rel })),
  ];
}

/** The canonical files to write and the legacy files to delete; none when there is no layout to convert. */
function layoutChange(root: string): [Map<string, string>, Map<string, Buffer>] {
  if (sources(root).length === 0) return [new Map(), new Map()];
  const layout = classify(root);
  if (layout.state === 'canonical') return [new Map(), new Map()];
  if (layout.state !== 'legacy') throw new MigrateError(layout.message ?? '');
  const legacy = new Map(layout.legacyFiles.map((rel) => [rel, readFileSync(join(root, rel))]));
  const outputs = new Map([[modelFile(), mergedModel(layout.legacyFiles.map((rel) => layout.scans.get(rel) as FileScan))]]);
  if (!layout.viewsExists) outputs.set(viewsFile(), EMPTY_VIEWS);
  verify(
    root,
    layout.legacyFiles.map((rel) => join(root, rel)),
    outputs,
  );
  return [outputs, legacy];
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
  const [outputs, legacy] = layoutChange(root);
  return write(root, outputs, legacy, text);
}

/** `la-arch-migrate`: print each written and deleted path, or exit 2 having changed nothing. */
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
