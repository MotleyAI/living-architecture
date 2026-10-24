// The constrained `.c4` model parser (element FQN = dotted path; relations resolve inside their root).
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { WORD, architecture, message, splitLines } from '../contract/index.js';

export interface Element {
  id: string;
  kind: string;
  title: string;
  parent: string | null;
  virtual: boolean;
  hasMetadata: boolean;
  metadata: Record<string, string | string[]>;
  metadataProblems: string[];
}

export interface Relation {
  src: string;
  dst: string;
  legacy: boolean;
}

/** A 0-based (line, column) position: the `splitLines` line index and the offset within that line. */
export type Pos = [number, number];

/** (start, end) positions, end exclusive, of an element's metadata block and of each key's statement. */
export interface MetadataSpan {
  block: [Pos, Pos];
  keys: Map<string, [Pos, Pos]>;
}

export interface ModelParse {
  elements: Element[];
  relations: Relation[];
  findings: string[];
  metadataFindings: string[];
  spans: Map<string, MetadataSpan>;
}

const ELEMENT_RE = new RegExp(String.raw`^(${WORD}+)\s*=\s*(${WORD}+)\s+'([^']*)'(?:\s*\{)?\s*$`, 'u');
const RELATION_RE = /^([\p{L}\p{N}_.]+)\s*->\s*([\p{L}\p{N}_.]+)(\s+#legacy)?\s*$/u;
const SPEC_ELEMENT_RE = new RegExp(String.raw`^element\s+(${WORD}+)(?:\s*\{)?\s*$`, 'u');
const TAG_DECL_RE = new RegExp(String.raw`^tag\s+${WORD}+$`, 'u');
const BLOCK_RE = new RegExp(`^(specification|model|views)(?!${WORD})`, 'u');
const BRACES_ONLY_RE = /^[{}]+$/;
const METADATA_OPEN_RE = /^metadata\s*\{$/;
const QUOTED = "'[^']*'";
const META_STMT_RE = new RegExp(String.raw`\s*(${WORD}+)\s+(${QUOTED}|\[\s*(?:${QUOTED}(?:\s*,\s*${QUOTED})*)?\s*\])`, 'uy');
const META_OPEN_ARRAY_RE = new RegExp(String.raw`^\s*${WORD}+\s+\[\s*(?:${QUOTED}(?:\s*,\s*${QUOTED})*\s*,?)?\s*$`, 'u');
const QUOTED_RE = new RegExp(QUOTED, 'g');
const SPEC_SPLIT_RE = new RegExp(String.raw`\s+(?=(?:element|tag)(?!${WORD}))`, 'u');

export function isOrAncestor(anc: string, eid: string): boolean {
  return anc === eid || eid.startsWith(`${anc}.`);
}

/** Drop a trailing `//` comment, leaving single-quoted spans untouched. */
export function stripLineComment(line: string): string {
  let inQuote = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === "'") inQuote = !inQuote;
    else if (!inQuote && line.startsWith('//', i)) return line.slice(0, i);
  }
  return line;
}

function braceDelta(code: string): number {
  let depth = 0;
  let inQuote = false;
  for (const ch of code) {
    if (ch === "'") inQuote = !inQuote;
    else if (!inQuote && ch === '{') depth += 1;
    else if (!inQuote && ch === '}') depth -= 1;
  }
  return depth;
}

/** Comment-stripped (line index, column, code) pieces with every unquoted `{`/`}` broken onto its own piece. */
function logicalLines(text: string): [number, number, string][] {
  const out: [number, number, string][] = [];
  let inQuote = false;
  splitLines(text)
    .map(stripLineComment)
    .forEach((line, index) => {
      let start = 0;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (ch === "'") inQuote = !inQuote;
        else if (!inQuote && ch === '{') {
          addPiece(out, index, line.slice(start, i + 1), start);
          start = i + 1;
        } else if (!inQuote && ch === '}') {
          addPiece(out, index, line.slice(start, i), start);
          addPiece(out, index, ch, i);
          start = i + 1;
        }
      }
      addPiece(out, index, line.slice(start), start);
    });
  return out;
}

function addPiece(out: [number, number, string][], index: number, piece: string, start: number): void {
  const code = piece.trim();
  if (code !== '') out.push([index, start + piece.length - piece.trimStart().length, code]);
}

interface Scan {
  kinds: Map<string, boolean>;
  byId: Map<string, Element>;
  duplicates: Set<string>;
  relations: Relation[];
  relPairs: Set<string>;
  findings: string[];
  metadataFindings: string[];
  spans: Map<string, MetadataSpan>;
}

/** An open `metadata { }` block; `element` is null when its content is discarded. */
interface MetadataBlock {
  element: string | null;
  start: Pos;
  depth: number;
  lines: [number, number, string][];
}

/** Where the scan of one model text stands: open region, brace depth, enclosing elements, open metadata block. */
interface TextState {
  region: string | null;
  depth: number;
  parents: string[];
  specKind: string | null;
  meta: MetadataBlock | null;
}

/** A metadata block's statements: the values, the text of each bad one, and each key's span. */
interface Statements {
  values: Map<string, string | string[]>;
  problems: string[];
  keys: Map<string, [Pos, Pos]>;
}

/** One metadata line at `at`, prefixed (up to `base`) by an unfinished array statement that starts at `carried`. */
interface MetadataText {
  text: string;
  base: number;
  at: Pos;
  carried: Pos;
}

/** Where `offset` in `piece.text` sits; any offset in the carried prefix maps to the carried statement's start. */
const posIn = (piece: MetadataText, offset: number): Pos =>
  offset < piece.base ? piece.carried : [piece.at[0], piece.at[1] + offset - piece.base];

/** Parse `architecture/model.c4` under the constrained authoring convention. */
export function parseModel(root: string): ModelParse {
  return parseModelFiles([join(root, architecture().model_file)]);
}

/** Parse `paths` in order as one model. */
export function parseModelFiles(paths: string[]): ModelParse {
  return parseModelTexts(paths.map((path) => readFileSync(path, 'utf8')));
}

/** Parse `texts` in order as one model; `spans` index the lines of the text each element is declared in. */
export function parseModelTexts(texts: string[]): ModelParse {
  const scan: Scan = {
    kinds: new Map(),
    byId: new Map(),
    duplicates: new Set(),
    relations: [],
    relPairs: new Set(),
    findings: [],
    metadataFindings: [],
    spans: new Map(),
  };
  for (const text of texts) scanModelText(text, scan);
  const elements = [...scan.byId.values()];
  for (const element of elements) {
    if (!scan.kinds.has(element.kind)) {
      scan.findings.push(message('c4.undeclared-kind', { element: element.id, kind: element.kind }));
    }
    element.virtual = scan.kinds.get(element.kind) ?? false;
  }
  for (const relation of scan.relations) {
    for (const endpoint of [relation.src, relation.dst]) {
      if (!scan.byId.has(endpoint)) {
        scan.findings.push(message('c4.unknown-endpoint', { src: relation.src, dst: relation.dst, endpoint }));
      }
    }
  }
  return {
    elements,
    relations: scan.relations,
    findings: scan.findings,
    metadataFindings: scan.metadataFindings,
    spans: scan.spans,
  };
}

function scanModelText(text: string, scan: Scan): void {
  const state: TextState = { region: null, depth: 0, parents: [], specKind: null, meta: null };
  let end: Pos = [0, 0];
  for (const [lineno, col, code] of logicalLines(text)) {
    end = [lineno, col + code.length];
    if (state.region === null) enterRegion(state, code);
    else if (state.meta !== null) metadataLine(state, state.meta, scan, [lineno, col], code);
    else if (state.region === 'model' && state.parents.length > 0 && METADATA_OPEN_RE.test(code)) {
      state.depth += braceDelta(code);
      state.meta = openMetadata(state.parents.at(-1) ?? '', code, scan, [lineno, col]);
    } else regionLine(state, scan, code);
  }
  if (state.meta !== null) closeMetadata(state.meta, scan, end);
}

function enterRegion(state: TextState, code: string): void {
  const m = BLOCK_RE.exec(code);
  if (m === null) return;
  state.region = m[1] === 'specification' || m[1] === 'model' ? (m[1] ?? null) : 'other';
  state.depth = braceDelta(code);
  if (state.depth <= 0) state.region = null;
}

function metadataLine(state: TextState, meta: MetadataBlock, scan: Scan, at: Pos, code: string): void {
  const delta = braceDelta(code);
  state.depth += delta;
  meta.depth += delta;
  if (meta.depth > 0) meta.lines.push([at[0], at[1], code]);
  else {
    closeMetadata(meta, scan, [at[0], at[1] + code.length]);
    state.meta = null;
  }
}

function regionLine(state: TextState, scan: Scan, code: string): void {
  const delta = braceDelta(code);
  if (state.region === 'specification') {
    for (const stmt of delta === 0 ? splitSpecStatements(code) : [code]) {
      state.specKind = scanSpecLine(stmt, scan, state.specKind, delta);
    }
  } else if (state.region === 'model') {
    scanModelLine(code, scan, state.parents, delta);
  }
  if (delta < 0) state.parents.splice(Math.max(0, state.parents.length + delta));
  state.depth += delta;
  if (state.depth <= 0) {
    state.region = null;
    state.parents.length = 0;
    state.specKind = null;
  } else if (state.region === 'specification' && state.depth === 1) {
    state.specKind = null;
  }
}

/** Start a block for `element`; a duplicate element's block, or a second block, is discarded. */
function openMetadata(element: string, code: string, scan: Scan, start: Pos): MetadataBlock {
  const target = scan.byId.get(element);
  if (scan.duplicates.has(element) || target === undefined) return { element: null, start, depth: 1, lines: [] };
  if (target.hasMetadata) {
    metadataProblem(scan, element, code);
    return { element: null, start, depth: 1, lines: [] };
  }
  target.hasMetadata = true;
  return { element, start, depth: 1, lines: [] };
}

function closeMetadata(block: MetadataBlock, scan: Scan, end: Pos): void {
  if (block.element === null) return;
  const parsed = parseMetadata(block.lines);
  const target = scan.byId.get(block.element);
  // fromEntries defines `__proto__` as an own key; assignment would hit the prototype setter.
  if (target !== undefined) target.metadata = Object.fromEntries(parsed.values);
  scan.spans.set(block.element, { block: [block.start, end], keys: parsed.keys });
  for (const line of parsed.problems) metadataProblem(scan, block.element, line);
}

function metadataProblem(scan: Scan, element: string, line: string): void {
  const problem = message('c4.malformed-metadata', { element, line });
  scan.byId.get(element)?.metadataProblems.push(problem);
  scan.metadataFindings.push(problem);
}

/** `key 'v'` / `key ['a', 'b']` statements (arrays may span lines) of (line, column, code) pieces. */
function parseMetadata(lines: [number, number, string][]): Statements {
  const out: Statements = { values: new Map(), problems: [], keys: new Map() };
  let carried = '';
  let carriedAt: Pos = [0, 0];
  for (const [lineno, col, line] of lines) {
    const piece: MetadataText = {
      text: carried ? `${carried} ${line}` : line,
      base: carried ? carried.length + 1 : 0,
      at: [lineno, col],
      carried: carriedAt,
    };
    [carried, carriedAt] = parseStatements(piece, out);
  }
  if (carried) out.problems.push(carried);
  return out;
}

/** Record `piece`'s statements in `out`; the unfinished array statement it ends with ('' if none) and its start. */
function parseStatements(piece: MetadataText, out: Statements): [string, Pos] {
  const { text } = piece;
  let pos = 0;
  while (pos < text.length) {
    META_STMT_RE.lastIndex = pos;
    const m = META_STMT_RE.exec(text);
    if (m === null) {
      const tail = text.slice(pos);
      const rest = tail.trim();
      if (META_OPEN_ARRAY_RE.test(rest)) return [rest, posIn(piece, pos + tail.length - tail.trimStart().length)];
      if (rest) out.problems.push(rest);
      break;
    }
    recordStatement(m, piece, out);
    pos = META_STMT_RE.lastIndex;
  }
  return ['', [0, 0]];
}

function recordStatement(m: RegExpExecArray, piece: MetadataText, out: Statements): void {
  const [whole, key = '', raw = ''] = m;
  if (out.values.has(key)) {
    out.problems.push(whole.trim());
    return;
  }
  out.values.set(key, raw.startsWith("'") ? raw.slice(1, -1) : (raw.match(QUOTED_RE) ?? []).map((q) => q.slice(1, -1)));
  const start = m.index + whole.length - whole.trimStart().length;
  out.keys.set(key, [posIn(piece, start), posIn(piece, m.index + whole.length)]);
}

/** Split a brace-free specification line into its `element`/`tag` statements. */
function splitSpecStatements(code: string): string[] {
  return code.split(SPEC_SPLIT_RE).filter((part) => part !== '');
}

function scanSpecLine(code: string, scan: Scan, specKind: string | null, delta: number): string | null {
  const m = SPEC_ELEMENT_RE.exec(code);
  if (m !== null) {
    const kind = m[1] ?? '';
    if (!scan.kinds.has(kind)) scan.kinds.set(kind, false);
    return delta > 0 ? kind : specKind;
  }
  if (TAG_DECL_RE.test(code) || BRACES_ONLY_RE.test(code)) return specKind;
  if (code.startsWith('#') && specKind !== null && code === '#virtual') {
    scan.kinds.set(specKind, true);
    return specKind;
  }
  scan.findings.push(message('c4.unrecognized-spec-line', { line: code }));
  return specKind;
}

function scanModelLine(code: string, scan: Scan, parents: string[], delta: number): void {
  const parent = parents.at(-1) ?? null;
  const m = ELEMENT_RE.exec(code);
  if (m !== null) {
    const [, local = '', kind = '', title = ''] = m;
    const eid = parent !== null ? `${parent}.${local}` : local;
    if (scan.byId.has(eid)) {
      scan.findings.push(message('c4.duplicate-element', { element: eid }));
      scan.duplicates.add(eid);
    } else {
      scan.byId.set(eid, {
        id: eid,
        kind,
        title,
        parent,
        virtual: false,
        hasMetadata: false,
        metadata: {},
        metadataProblems: [],
      });
    }
    if (delta > 0) parents.push(eid);
    return;
  }
  const rel = RELATION_RE.exec(code);
  if (rel !== null) scanRelation(rel, scan, parents);
  else if (!BRACES_ONLY_RE.test(code)) scan.findings.push(message('c4.unrecognized-model-line', { line: code }));
}

function scanRelation(rel: RegExpExecArray, scan: Scan, parents: string[]): void {
  let [, src = '', dst = ''] = rel;
  const legacy = rel[3] !== undefined;
  const parent = parents.at(-1);
  if (parent === undefined) {
    scan.findings.push(message('c4.relation-outside-root', { src, dst }));
    return;
  }
  if (parents.length > 1) {
    scan.findings.push(message('c4.relation-in-body', { src, dst, parent }));
    return;
  }
  [src, dst] = [`${parent}.${src}`, `${parent}.${dst}`];
  const pair = `${src}\0${dst}`;
  if (scan.relPairs.has(pair)) scan.findings.push(message('c4.duplicate-relation', { src, dst }));
  else {
    scan.relPairs.add(pair);
    scan.relations.push({ src, dst, legacy });
  }
}

/** The elements and relations under `root`, with the root prefix stripped (the root itself dropped). */
export function project(model: ModelParse, root: string): ModelParse {
  const prefix = `${root}.`;
  const local = (eid: string): string => eid.slice(prefix.length);
  return {
    elements: model.elements
      .filter((e) => e.id.startsWith(prefix))
      .map((e) => ({ ...e, id: local(e.id), parent: e.parent === root ? null : local(e.parent ?? '') })),
    relations: model.relations
      .filter((r) => r.src.startsWith(prefix) && r.dst.startsWith(prefix))
      .map((r) => ({ src: local(r.src), dst: local(r.dst), legacy: r.legacy })),
    findings: [],
    metadataFindings: [],
    spans: new Map(),
  };
}

/** Top-level element ids, in model order. */
export function roots(model: ModelParse): string[] {
  return model.elements.filter((e) => e.parent === null).map((e) => e.id);
}
