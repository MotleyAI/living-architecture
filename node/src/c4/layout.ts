// The canonical LikeC4 layout: exactly `architecture/model.c4` and `architecture/views.c4`, each with its blocks.
import { lstatSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { architecture, byCodePoint, message } from '../contract/index.js';
import { stripLineComment } from './model.js';

const WORD_RE = /[A-Za-z0-9_]+/y;
export const WHITESPACE = ' \t\n\r\f\v';

/** Strip WHITESPACE (only) from both ends. */
export function stripWhitespace(text: string): string {
  let start = 0;
  let end = text.length;
  while (start < end && WHITESPACE.includes(text[start] ?? '')) start += 1;
  while (end > start && WHITESPACE.includes(text[end - 1] ?? '')) end -= 1;
  return text.slice(start, end);
}

/** A top-level `<kind> { }` block; `close` is the offset of its `}`, null when unclosed. */
export interface Block {
  kind: string;
  line: number;
  start: number;
  open: number;
  close: number | null;
}

interface Problem {
  offset: number;
  line: number;
  id: string;
  text: string;
}

/** One LikeC4 source: its text, top-level blocks and lexical problems, in file order. */
export interface FileScan {
  text: string;
  blocks: Block[];
  problems: Problem[];
}

/** The classified layout of `architecture/`; `message` is null exactly when it is canonical. */
export interface Layout {
  state: 'canonical' | 'legacy' | 'other';
  message: string | null;
  legacyFiles: string[];
  scans: Map<string, FileScan>;
  viewsExists: boolean;
}

export const modelFile = (): string => architecture().model_file;
export const viewsFile = (): string => architecture().views_file;
export const legacyModelDir = (): string => architecture().legacy_model_dir;
const allowedBlocks = (rel: string): string[] => architecture().blocks[rel];

function lineOf(text: string, offset: number): number {
  let line = 1;
  for (let i = text.indexOf('\n'); i !== -1 && i < offset; i = text.indexOf('\n', i + 1)) line += 1;
  return line;
}

function lineEnd(text: string, pos: number): number {
  const end = text.indexOf('\n', pos);
  return end < 0 ? text.length : end;
}

/** Past whitespace and `//` comments. */
function skipTrivia(text: string, pos: number): number {
  while (pos < text.length) {
    if (WHITESPACE.includes(text[pos] ?? '')) pos += 1;
    else if (text.startsWith('//', pos)) pos = lineEnd(text, pos);
    else break;
  }
  return pos;
}

/**
 * Walk from `pos` at brace `depth` (quote- and comment-aware) to where depth returns to 0.
 * `stopAtEol`: also stop at a newline or an unmatched `}` reached at depth 0. Returns [offset, final depth].
 */
function balancedEnd(text: string, pos: number, depth: number, stopAtEol: boolean): [number, number] {
  let inQuote = false;
  while (pos < text.length) {
    const ch = text[pos];
    if (ch === '\n') {
      inQuote = false;
      if (stopAtEol && depth === 0) return [pos, 0];
    } else if (inQuote) {
      inQuote = ch !== "'";
    } else if (ch === "'") {
      inQuote = true;
    } else if (text.startsWith('//', pos)) {
      pos = lineEnd(text, pos);
      continue;
    } else if (ch === '{') {
      depth += 1;
    } else if (ch === '}') {
      if (depth === 0) return [pos, 0];
      depth -= 1;
      if (depth === 0 && !stopAtEol) return [pos, 0];
    }
    pos += 1;
  }
  return [pos, depth];
}

/** Split `text` into top-level blocks; anything else but whitespace and comments is a problem. */
export function scan(text: string): FileScan {
  const blocks: Block[] = [];
  const problems: Problem[] = [];
  const problem = (offset: number, id: string, shown = ''): void => {
    problems.push({ offset, line: lineOf(text, offset), id, text: shown });
  };
  let pos = skipTrivia(text, 0);
  while (pos < text.length) {
    WORD_RE.lastIndex = pos;
    const word = WORD_RE.exec(text);
    const brace = word ? skipTrivia(text, pos + word[0].length) : pos;
    if (word && text[brace] === '{') {
      const [close, depth] = balancedEnd(text, brace + 1, 1, false);
      const closed = depth === 0 && close < text.length;
      blocks.push({ kind: word[0], line: lineOf(text, pos), start: pos, open: brace, close: closed ? close : null });
      if (!closed) {
        problem(pos, 'c4-layout.unbalanced-braces');
        break;
      }
      pos = skipTrivia(text, close + 1);
      continue;
    }
    if (text[pos] === '}') {
      problem(pos, 'c4-layout.unbalanced-braces');
      pos = skipTrivia(text, pos + 1);
      continue;
    }
    const [end, depth] = balancedEnd(text, pos, 0, true);
    problem(pos, 'c4-layout.top-level-text', stripWhitespace(stripLineComment(text.slice(pos, end).split('\n')[0] ?? '')));
    if (depth > 0) problem(pos, 'c4-layout.unbalanced-braces');
    pos = skipTrivia(text, end);
  }
  return { text, blocks, problems };
}

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

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/** Every LikeC4 source file under `architecture/`, repo-relative, in code-point order. */
export function sources(root: string): string[] {
  if (!isDirectory(join(root, 'architecture'))) return [];
  const extensions: string[] = architecture().source_extensions;
  const found: string[] = [];
  const walk = (rel: string): void => {
    for (const entry of readdirSync(join(root, rel), { withFileTypes: true })) {
      const child = `${rel}/${entry.name}`;
      if (entry.isDirectory()) walk(child);
      else if (extensions.some((ext) => entry.name.endsWith(ext)) && isFile(join(root, child))) found.push(child);
    }
  };
  walk('architecture');
  return found.sort(byCodePoint);
}

const render = (rel: string, p: Problem): string => message(p.id, { path: rel, line: p.line, text: p.text });

/** The block rules of one canonical file, in file order; missing blocks last. */
function blockViolations(rel: string, fileScan: FileScan): string[] {
  const allowed = allowedBlocks(rel);
  const found: [number, string][] = fileScan.problems.map((p) => [p.offset, render(rel, p)]);
  const seen = new Set<string>();
  for (const block of fileScan.blocks) {
    const values = { path: rel, line: block.line, block: block.kind };
    if (!allowed.includes(block.kind)) found.push([block.start, message('c4-layout.block-not-allowed', values)]);
    else if (seen.has(block.kind)) found.push([block.start, message('c4-layout.block-duplicate', values)]);
    seen.add(block.kind);
  }
  const lines = found.sort((a, b) => a[0] - b[0]).map(([, text]) => text);
  return [
    ...lines,
    ...allowed.filter((kind) => !seen.has(kind)).map((kind) => message('c4-layout.block-missing', { path: rel, block: kind })),
  ];
}

function strayViolations(rel: string, fileScan: FileScan): string[] {
  const kinds = [...new Set(fileScan.blocks.map((block) => block.kind))];
  const holding = kinds.length > 0 ? kinds.map((kind) => `\`${kind}\``).join(', ') : message('c4-layout.no-blocks');
  return [message('c4-layout.stray', { path: rel, blocks: holding }), ...fileScan.problems.map((p) => render(rel, p))];
}

function canonicalState(root: string, rel: string): 'file' | 'missing' | 'not-a-file' {
  const path = join(root, rel);
  if (isFile(path)) return 'file';
  return lexists(path) ? 'not-a-file' : 'missing';
}

function isLegacyFile(rel: string, fileScan: FileScan): boolean {
  const directlyInModelDir = rel.slice(0, rel.lastIndexOf('/')) === legacyModelDir() && rel.endsWith('.c4');
  const allowed = allowedBlocks(modelFile());
  return directlyInModelDir && fileScan.problems.length === 0 && fileScan.blocks.every((b) => allowed.includes(b.kind));
}

/** Discover, scan and classify every LikeC4 source under `architecture/`. */
export function classify(root: string): Layout {
  const canonical = [modelFile(), viewsFile()];
  const states = new Map(canonical.map((rel) => [rel, canonicalState(root, rel)]));
  const strays = sources(root).filter((rel) => !canonical.includes(rel));
  const scans = new Map<string, FileScan>();
  for (const rel of [...strays, ...canonical.filter((r) => states.get(r) === 'file')]) {
    scans.set(rel, scan(readFileSync(join(root, rel), 'utf8')));
  }
  const scanOf = (rel: string): FileScan => scans.get(rel) as FileScan;
  const violations = new Map<string, string[]>();
  for (const rel of canonical) {
    const state = states.get(rel);
    violations.set(rel, state === 'file' ? blockViolations(rel, scanOf(rel)) : [message(`c4-layout.${state}`, { path: rel })]);
  }
  for (const rel of strays) violations.set(rel, strayViolations(rel, scanOf(rel)));
  const lines = [...violations.keys()].sort(byCodePoint).flatMap((rel) => violations.get(rel) ?? []);
  const viewsExists = states.get(viewsFile()) === 'file';
  if (lines.length === 0) return { state: 'canonical', message: null, legacyFiles: [], scans, viewsExists };
  const legacy =
    strays.length > 0 &&
    states.get(modelFile()) === 'missing' &&
    strays.every((rel) => isLegacyFile(rel, scanOf(rel))) &&
    (states.get(viewsFile()) === 'missing' || (viewsExists && (violations.get(viewsFile()) ?? []).length === 0));
  const tail = message(legacy ? 'c4-layout.migrate' : 'c4-layout.merge-by-hand');
  return {
    state: legacy ? 'legacy' : 'other',
    message: [message('c4-layout.header'), ...lines, tail].join('\n'),
    legacyFiles: legacy ? strays : [],
    scans,
    viewsExists,
  };
}

/** The layout message naming every violation, or null when the layout is canonical. */
export function layoutProblem(root: string): string | null {
  return classify(root).message;
}
