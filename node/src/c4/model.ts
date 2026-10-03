// The constrained `.c4` model parser (element FQN = dotted path; relations resolve inside their root).
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { WORD, message, splitLines } from '../contract/index.js';

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

export interface ModelParse {
  elements: Element[];
  relations: Relation[];
  findings: string[];
  metadataFindings: string[];
}

const ELEMENT_RE = new RegExp(`^(${WORD}+)\\s*=\\s*(${WORD}+)\\s+'([^']*)'(?:\\s*\\{)?\\s*$`, 'u');
const RELATION_RE = new RegExp(`^([\\p{L}\\p{N}_.]+)\\s*->\\s*([\\p{L}\\p{N}_.]+)(\\s+#legacy)?\\s*$`, 'u');
const SPEC_ELEMENT_RE = new RegExp(`^element\\s+(${WORD}+)(?:\\s*\\{)?\\s*$`, 'u');
const TAG_DECL_RE = new RegExp(`^tag\\s+${WORD}+$`, 'u');
const BLOCK_RE = new RegExp(`^(specification|model|views)(?!${WORD})`, 'u');
const BRACES_ONLY_RE = /^[{}]+$/;
const METADATA_OPEN_RE = /^metadata\s*\{$/;
const QUOTED = "'[^']*'";
const META_STMT_RE = new RegExp(`\\s*(${WORD}+)\\s+(${QUOTED}|\\[\\s*(?:${QUOTED}(?:\\s*,\\s*${QUOTED})*)?\\s*\\])`, 'uy');
const META_OPEN_ARRAY_RE = new RegExp(`^\\s*${WORD}+\\s+\\[\\s*(?:${QUOTED}(?:\\s*,\\s*${QUOTED})*\\s*,?)?\\s*$`, 'u');
const QUOTED_RE = new RegExp(QUOTED, 'g');
const SPEC_SPLIT_RE = new RegExp(`\\s+(?=(?:element|tag)(?!${WORD}))`, 'u');

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

/** Comment-stripped lines with every unquoted `{`/`}` broken onto its own line. */
function logicalLines(text: string): string[] {
  const decommented = splitLines(text).map(stripLineComment).join('\n');
  let out = '';
  let inQuote = false;
  for (const ch of decommented) {
    if (ch === "'") {
      inQuote = !inQuote;
      out += ch;
    } else if (!inQuote && ch === '{') out += '{\n';
    else if (!inQuote && ch === '}') out += '\n}\n';
    else out += ch;
  }
  return splitLines(out)
    .map((line) => line.trim())
    .filter((line) => line !== '');
}

function modelFiles(root: string): string[] {
  const dir = join(root, 'architecture', 'model');
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  return names
    .filter((name) => name.endsWith('.c4') && statSync(join(dir, name)).isFile())
    .sort()
    .map((name) => join(dir, name));
}

interface Scan {
  kinds: Map<string, boolean>;
  byId: Map<string, Element>;
  duplicates: Set<string>;
  relations: Relation[];
  relPairs: Set<string>;
  findings: string[];
  metadataFindings: string[];
}

/** An open `metadata { }` block; `element` is null when its content is discarded. */
interface MetadataBlock {
  element: string | null;
  depth: number;
  lines: string[];
}

/** Parse `architecture/model/*.c4` under the constrained authoring convention. */
export function parseModel(root: string): ModelParse {
  const scan: Scan = {
    kinds: new Map(),
    byId: new Map(),
    duplicates: new Set(),
    relations: [],
    relPairs: new Set(),
    findings: [],
    metadataFindings: [],
  };
  for (const path of modelFiles(root)) scanModelFile(readFileSync(path, 'utf8'), scan);
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
  return { elements, relations: scan.relations, findings: scan.findings, metadataFindings: scan.metadataFindings };
}

function scanModelFile(text: string, scan: Scan): void {
  let region: string | null = null;
  let depth = 0;
  const parents: string[] = [];
  let specKind: string | null = null;
  let meta: MetadataBlock | null = null;
  for (const code of logicalLines(text)) {
    if (region === null) {
      const m = BLOCK_RE.exec(code);
      if (m !== null) {
        region = m[1] === 'specification' || m[1] === 'model' ? (m[1] ?? null) : 'other';
        depth = braceDelta(code);
        if (depth <= 0) region = null;
      }
      continue;
    }
    const delta = braceDelta(code);
    if (meta !== null) {
      depth += delta;
      meta.depth += delta;
      if (meta.depth > 0) meta.lines.push(code);
      else {
        closeMetadata(meta, scan);
        meta = null;
      }
      continue;
    }
    if (region === 'model' && parents.length > 0 && METADATA_OPEN_RE.test(code)) {
      depth += delta;
      meta = openMetadata(parents[parents.length - 1] ?? '', code, scan);
      continue;
    }
    if (region === 'specification') {
      for (const stmt of delta === 0 ? splitSpecStatements(code) : [code]) {
        specKind = scanSpecLine(stmt, scan, specKind, delta);
      }
    } else if (region === 'model') {
      scanModelLine(code, scan, parents, delta);
    }
    if (delta < 0) for (let i = 0; i < -delta; i += 1) parents.pop();
    depth += delta;
    if (depth <= 0) {
      region = null;
      parents.length = 0;
      specKind = null;
    } else if (region === 'specification' && depth === 1) {
      specKind = null;
    }
  }
  if (meta !== null) closeMetadata(meta, scan);
}

/** Start a block for `element`; a duplicate element's block, or a second block, is discarded. */
function openMetadata(element: string, code: string, scan: Scan): MetadataBlock {
  const target = scan.byId.get(element);
  if (scan.duplicates.has(element) || target === undefined) return { element: null, depth: 1, lines: [] };
  if (target.hasMetadata) {
    metadataProblem(scan, element, code);
    return { element: null, depth: 1, lines: [] };
  }
  target.hasMetadata = true;
  return { element, depth: 1, lines: [] };
}

function closeMetadata(block: MetadataBlock, scan: Scan): void {
  if (block.element === null) return;
  const [values, problems] = parseMetadata(block.lines);
  const target = scan.byId.get(block.element);
  if (target !== undefined) target.metadata = values;
  for (const line of problems) metadataProblem(scan, block.element, line);
}

function metadataProblem(scan: Scan, element: string, line: string): void {
  const problem = message('c4.malformed-metadata', { element, line });
  scan.byId.get(element)?.metadataProblems.push(problem);
  scan.metadataFindings.push(problem);
}

/** `key 'v'` / `key ['a', 'b']` statements (arrays may span lines) and the text of each bad one. */
function parseMetadata(lines: string[]): [Record<string, string | string[]>, string[]] {
  const values = new Map<string, string | string[]>();
  const problems: string[] = [];
  let pending = '';
  for (const line of lines) {
    const text = pending ? `${pending} ${line}` : line;
    pending = '';
    let pos = 0;
    while (pos < text.length) {
      META_STMT_RE.lastIndex = pos;
      const m = META_STMT_RE.exec(text);
      if (m === null) {
        const rest = text.slice(pos).trim();
        if (META_OPEN_ARRAY_RE.test(rest)) pending = rest;
        else if (rest) problems.push(rest);
        break;
      }
      const [whole, key = '', raw = ''] = m;
      if (values.has(key)) problems.push(whole.trim());
      else values.set(key, raw.startsWith("'") ? raw.slice(1, -1) : (raw.match(QUOTED_RE) ?? []).map((q) => q.slice(1, -1)));
      pos = META_STMT_RE.lastIndex;
    }
  }
  if (pending) problems.push(pending);
  // fromEntries defines `__proto__` as an own key; assignment would hit the prototype setter.
  return [Object.fromEntries(values), problems];
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
  const parent = parents[parents.length - 1] ?? null;
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
  if (rel !== null) {
    let [, src = '', dst = ''] = rel;
    const legacy = rel[3] !== undefined;
    if (parent === null) {
      scan.findings.push(message('c4.relation-outside-root', { src, dst }));
      return;
    }
    if (parents.length > 1) {
      scan.findings.push(message('c4.relation-in-body', { src, dst, parent }));
      return;
    }
    [src, dst] = [`${parents[0]}.${src}`, `${parents[0]}.${dst}`];
    const pair = `${src}\0${dst}`;
    if (scan.relPairs.has(pair)) scan.findings.push(message('c4.duplicate-relation', { src, dst }));
    else {
      scan.relPairs.add(pair);
      scan.relations.push({ src, dst, legacy });
    }
    return;
  }
  if (BRACES_ONLY_RE.test(code)) return;
  scan.findings.push(message('c4.unrecognized-model-line', { line: code }));
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
  };
}

/** Top-level element ids, in model order. */
export function roots(model: ModelParse): string[] {
  return model.elements.filter((e) => e.parent === null).map((e) => e.id);
}
