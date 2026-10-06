// `la-arch-migrate`: merge the legacy `architecture/model/*.c4` model into `architecture/model.c4`, verified.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, rmdirSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { message } from '../contract/index.js';
import { type FileScan, classify, legacyModelDir, modelFile, stripWhitespace, viewsFile } from './layout.js';
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
  if (lines[lines.length - 1] === '') lines.pop();
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
  return { ...model, findings: [...model.findings].sort(), metadataFindings: [...model.metadataFindings].sort() };
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

const attempt = (step: () => void): void => {
  try {
    step();
  } catch {
    // best-effort undo
  }
};

/** Create every output, delete the legacy files and an emptied model dir; undo it all on an error. */
function write(root: string, outputs: Map<string, string>, legacy: Map<string, Buffer>): string[] {
  const created: string[] = [];
  const deleted: string[] = [];
  const modelDir = join(root, legacyModelDir());
  let removedDir = false;
  try {
    for (const [rel, text] of outputs) {
      const path = join(root, rel);
      created.push(path);
      try {
        writeFileSync(path, text, { encoding: 'utf8', flag: 'wx' });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'EEXIST') created.pop();
        throw error;
      }
    }
    for (const rel of legacy.keys()) {
      unlinkSync(join(root, rel));
      deleted.push(rel);
    }
    if (readdirSync(modelDir).length === 0) {
      rmdirSync(modelDir);
      removedDir = true;
    }
  } catch (error) {
    if (removedDir) attempt(() => mkdirSync(modelDir));
    for (const rel of deleted) attempt(() => writeFileSync(join(root, rel), legacy.get(rel) as Buffer));
    for (const path of created) attempt(() => unlinkSync(path));
    throw error;
  }
  const report = [...outputs.keys()].map((rel) => message('arch-migrate.written', { path: rel }));
  report.push(...deleted.map((rel) => message('arch-migrate.deleted', { path: rel })));
  if (removedDir) report.push(message('arch-migrate.deleted', { path: legacyModelDir() }));
  return report;
}

/** Migrate the repo at `root`; the lines to print. Throws (having written nothing) when it cannot. */
export function migrate(root: string): string[] {
  const layout = classify(root);
  if (layout.state === 'canonical') return [message('arch-migrate.nothing')];
  if (layout.state !== 'legacy') throw new MigrateError(layout.message ?? '');
  const legacy = new Map(layout.legacyFiles.map((rel) => [rel, readFileSync(join(root, rel))]));
  const outputs = new Map([[modelFile(), mergedModel(layout.legacyFiles.map((rel) => layout.scans.get(rel) as FileScan))]]);
  if (!layout.viewsExists) outputs.set(viewsFile(), EMPTY_VIEWS);
  verify(
    root,
    layout.legacyFiles.map((rel) => join(root, rel)),
    outputs,
  );
  return write(root, outputs, legacy);
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
