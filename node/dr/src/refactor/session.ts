// One `dr-refactor` run on TypeScript: the project's services, the locators, and the output with its apply.
import { isAbsolute, relative, sep } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint, message, readFile } from '../contract/index.js';
import { posix, ts } from '../lang/index.js';
import { alignBaseline, baselineRuns } from './baseline.js';
import { CHECKER_OPTIONS } from './compliance.js';
import { unifiedDiff } from './diff.js';
import { applyEdits, type Edit, RefactorError, splitBom } from './edits.js';
import { Lines } from './lines.js';
import type { MovedSpan } from './position.js';
import { Progress } from './progress.js';
import { languageFiles, realPath, under } from './routing.js';
import { timed } from './timings.js';
import { type Located, locate as locateSymbol, locateEvery as locateEverySymbol } from './symbols.js';
import { Workspace } from './workspace.js';
import { type Write, writeAll } from './writer.js';

export interface RefactorArgs {
  project: string;
  apply: boolean;
  timings?: boolean;
  subcommand: 'rename' | 'rename-map' | 'generate-map' | 'retarget' | 'move-symbol' | 'move-module';
  file?: string;
  offset?: number;
  line?: number;
  col?: number;
  symbol?: string;
  new_name?: string;
  target?: string;
  map?: string;
  in_hierarchy?: boolean;
  unsure?: string;
  allow_blindspots?: boolean;
  with_stand_ins?: string[];
  without_stand_ins?: string[];
  keep?: string[];
  keep_literal?: string[];
  docs?: boolean;
  docs_pick?: string[];
  words?: string;
  table?: string;
  language?: string;
  fail_fast?: boolean;
  stub?: string;
  dest?: string;
  module?: string;
}

/** Where a symbol is: an offset, a 1-based line and column, or a declaration's path in the file. */
export interface Locator {
  offset?: number;
  line?: number;
  col?: number;
  symbol?: string;
}

/** The command line or the map is wrong; the message is user-facing, exit 2. */
export class UsageError extends Error {}

interface Entry {
  path: string;
  text: string;
}

export class Refactor {
  readonly root: string;
  private readonly cwd = process.cwd();
  private workspaceCache: Workspace | null = null;

  constructor(readonly args: RefactorArgs) {
    this.root = realPath(under(this.cwd, args.project));
  }

  get workspace(): Workspace {
    this.workspaceCache ??= timed('load', () => new Workspace(this.root));
    return this.workspaceCache;
  }

  rel(path: string): string {
    return posix(relative(this.root, path));
  }

  /** `raw` from `base` (the working directory by default) with symlinks resolved; RefactorError when outside the project. */
  inProject(raw: string, base: string = this.cwd): string {
    const path = realPath(under(base, raw));
    const rel = relative(this.root, path);
    if (rel.split(sep)[0] === '..' || isAbsolute(rel)) throw new RefactorError(message('refactor.outside-project', { path: raw }));
    return path;
  }

  owner(file: string): void {
    if (this.workspace.owner(file) === null) throw new RefactorError(message('refactor.ts-outside-project', { path: this.rel(file) }));
  }

  /** The language services of the projects relevant to `file` whose program includes it, the owner's first. */
  services(file: string): TS.LanguageService[] {
    return this.workspace.holding(file);
  }

  /** The headers, one diff or rename pair per entry in path order (the realigned baseline among them), then the
   * footer; writes only with --apply, every file or none. */
  emit(headers: string[], edits: Map<string, Edit[]>, moves: [string, string][], spans: MovedSpan[] = [], progress: Progress = new Progress()): number {
    const entries: Entry[] = [];
    const writes: Write[] = [];
    for (const [path, fileEdits] of edits) {
      const old = readFile(path, 'utf8');
      const [bom, body] = splitBom(old);
      const analysed = this.services(path)[0]?.getProgram()?.getSourceFile(path)?.text;
      if (analysed !== undefined && body !== analysed) throw new RefactorError(message('refactor.file-changed', { path: this.rel(path) }));
      const text = bom + applyEdits(body, fileEdits);
      if (text !== old) writes.push({ path, old, text });
    }
    const texts = new Map(writes.map((w) => [w.path, splitBom(w.text)[1]]));
    if (baselineRuns(this)) progress.phase('baseline');
    const aligned = timed('baseline', () => alignBaseline(this, { edits, moves: new Map(moves), spans }, texts));
    process.stderr.write(aligned.warnings.map((line) => `${line}\n`).join(''));
    if (aligned.write !== null) writes.push(aligned.write);
    for (const { path, old, text } of writes) entries.push({ path: this.rel(path), text: unifiedDiff(old, text, this.rel(path)) });
    for (const [from, to] of moves) entries.push({ path: this.rel(from), text: message('refactor.moved', { old: this.rel(from), new: this.rel(to) }) });
    entries.sort((a, b) => byCodePoint(a.path, b.path));
    const paths = [...new Set(entries.map((e) => e.path))];
    const body = entries.map((e) => `${e.text}\n`).join('');
    let out = `${headers.join('\n')}\n\n\n${body}\n`;
    if (this.args.apply) {
      progress.phase('write');
      timed('write', () => writeAll(this.root, writes.toSorted((a, b) => byCodePoint(a.path, b.path)), moves, (path) => this.rel(path)));
      out += `${message('refactor.applied', { count: paths.length })}\n`;
      out += paths.map((path) => `${message('refactor.applied-file', { path })}\n`).join('');
    } else {
      out += `${message('refactor.dry-run', { count: paths.length })}\n`;
    }
    process.stdout.write(out);
    return 0;
  }
}

const codePoints = (text: string): string[] => [...text];

/** The UTF-16 offset of the code point offset `points` into `text`. */
const utf16 = (text: string, points: number): number => codePoints(text).slice(0, points).join('').length;

export function* nodes(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* nodes(child);
}

/** Where an offset or a line and column of `locator` points in `text`; null for any other locator. */
export function positionOf(text: string, locator: Locator): number | null {
  if (locator.offset !== undefined) return locateOffset(text, locator.offset);
  return locator.line === undefined ? null : locateLine(text, locator.line, locator.col ?? 1);
}

/** Every place `locator` points at in `file` (`shown` in messages): its offset, its line and column (code points),
 * the declaration its path names, or with `every` each local its wildcard path names. */
function locateAll(r: Refactor, file: string, shown: string, locator: Locator, follow: boolean, every: boolean): Located[] {
  const position = positionOf(readFile(file, 'utf8'), locator);
  if (position !== null) return [{ file, position, topLevel: false }];
  if (locator.symbol === undefined) throw new RefactorError(message('refactor.no-locator'));
  r.owner(file);
  const program = r.services(file)[0]?.getProgram();
  const source = program?.getSourceFile(file);
  if (program === undefined || source === undefined) throw new RefactorError(message('refactor.ts-outside-project', { path: r.rel(file) }));
  const checker = program.getTypeChecker();
  return every ? locateEverySymbol(checker, source, locator.symbol, shown) : [locateSymbol(checker, source, locator.symbol, shown, follow)];
}

/** Where `locator` points in `file`; a wildcard path is refused. */
export function locate(r: Refactor, file: string, shown: string, locator: Locator, follow = true): Located {
  return locateAll(r, file, shown, locator, follow, false)[0] as Located;
}

/** Where `locator` points in `file`, a wildcard path at each local it names. */
export function locateEvery(r: Refactor, file: string, shown: string, locator: Locator): Located[] {
  return locateAll(r, file, shown, locator, true, true);
}

function locateOffset(text: string, offset: number): number {
  const count = codePoints(text).length;
  if (offset < 0 || offset > count) throw new RefactorError(message('refactor.offset-out-of-range', { offset, count }));
  return utf16(text, offset);
}

function locateLine(text: string, line: number, col: number): number {
  const lines = new Lines(text);
  if (line < 1 || line > lines.count) throw new RefactorError(message('refactor.line-out-of-range', { line, count: lines.count }));
  const lineText = lines.lineText(line);
  const width = codePoints(lineText).length;
  if (col < 1 || col > width + 1) throw new RefactorError(message('refactor.col-out-of-range', { col, line, count: width }));
  return lines.start(line) + utf16(lineText, col - 1);
}

/** A source of the refactor's projects with the service and checker of the first program holding it. */
export interface ProjectSource {
  source: TS.SourceFile;
  service: TS.LanguageService;
  checker: TS.TypeChecker;
}

/** The project's TypeScript files (the files `dr-compliance` expands the project to), each from the first of
 * `services`' programs holding it, else from its governing project's program. */
export function projectSources(r: Refactor, services: TS.LanguageService[]): Map<string, ProjectSource> {
  const out = new Map<string, ProjectSource>();
  const rest: string[] = [];
  for (const path of languageFiles(r.root, 'typescript')) {
    const found = services.find((service) => service.getProgram()?.getSourceFile(path) !== undefined);
    const program = found?.getProgram();
    const source = program?.getSourceFile(path);
    if (found === undefined || program === undefined || source === undefined) rest.push(path);
    else out.set(source.fileName, { source, service: found, checker: program.getTypeChecker() });
  }
  for (const [path, service] of r.workspace.servicesOf(rest, CHECKER_OPTIONS)) {
    const program = service.getProgram();
    const source = program?.getSourceFile(path);
    if (program !== undefined && source !== undefined) out.set(source.fileName, { source, service, checker: program.getTypeChecker() });
  }
  return out;
}

/** The innermost node of `source` holding `position`. */
export function nodeAt(source: TS.SourceFile, position: number): TS.Node {
  let node: TS.Node = source;
  for (;;) {
    const inner: TS.Node | undefined =
      ts().forEachChild(node, (child) => (child.getStart(source) <= position && position < child.end ? child : undefined)) ??
      ts().forEachChild(node, (child) => (child.getStart(source) <= position && position <= child.end ? child : undefined));
    if (inner === undefined) return node;
    node = inner;
  }
}
