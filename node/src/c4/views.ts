// The constrained `views.c4` include grammar and view expansion over a root-local projection.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { architecture, isWordStart, message, splitLines } from '../contract/index.js';
import { readIndex } from './index-file.js';
import { type ModelParse, type Relation, isOrAncestor, project, roots, stripLineComment } from './model.js';

export interface Edge {
  src: string;
  dst: string;
  legacy: boolean;
}

/** A view of one language root; ids are local to the root. */
export interface View {
  id: string;
  title: string;
  root: string;
  nodeIds: string[];
  edges: Edge[];
}

export interface ViewsParse {
  views: View[];
  findings: string[];
}

/** A view's include grammar, parsed before the depth knob is known. */
interface RawView {
  id: string;
  title: string;
  root: string;
  base: string[];
  srcAnchors: Set<string>;
  dstAnchors: Set<string>;
}

type Token = [string, string];

const TOKEN_RE = /'[^']*'|->|[\p{L}\p{N}_.]+|\S/gu;

export const DEFAULT_VIEW_DEPTH = 3;

const level = (eid: string): number => eid.split('.').length;
const ancestorAtLevel = (eid: string, n: number): string => eid.split('.').slice(0, n).join('.');

function tokenize(text: string): Token[] {
  const stripped = splitLines(text).map(stripLineComment).join('\n');
  const tokens: Token[] = [];
  for (const [tok] of stripped.matchAll(TOKEN_RE)) {
    if (tok.startsWith("'")) tokens.push(['str', tok.slice(1, -1)]);
    else if (tok === '->') tokens.push(['arrow', tok]);
    else if (tok === '*') tokens.push(['star', tok]);
    else if ('{}(),'.includes(tok)) tokens.push([tok, tok]);
    else if (isWordStart([...tok][0] ?? '')) tokens.push(['word', tok]);
    else tokens.push(['unknown', tok]);
  }
  return tokens;
}

/** The root-local projection a view body is read against. */
interface Scope {
  root: string;
  model: ModelParse;
  topLevel: string[];
  known: Set<string>;
}

function scopeOf(model: ModelParse, root: string): Scope {
  const local = project(model, root);
  return {
    root,
    model: local,
    topLevel: local.elements.filter((e) => e.parent === null).map((e) => e.id),
    known: new Set(local.elements.map((e) => e.id)),
  };
}

function addBase(raw: RawView, name: string): void {
  if (!raw.base.includes(name)) raw.base.push(name);
}

const same = (a: Token, b: Token): boolean => a[0] === b[0] && a[1] === b[1];

/** The include grammar over one token stream; findings accumulate in order. */
class Parser {
  pos = 0;
  readonly findings: string[] = [];

  constructor(private readonly tokens: Token[]) {}

  cur(): Token {
    return this.tokens[this.pos] ?? ['eof', ''];
  }

  advance(): Token {
    const tok = this.cur();
    this.pos += 1;
    return tok;
  }

  private anchorOk(scope: Scope, name: string, form: string, findings: string[]): boolean {
    if (!scope.known.has(name)) {
      findings.push(message('c4.include-unknown', { form, name }));
      return false;
    }
    return true;
  }

  private readSpec(vid: string, scope: Scope, raw: RawView, findings: string[]): void {
    const tok = this.advance();
    if (tok[0] === 'star') this.readStar(vid, scope, raw, findings);
    else if (tok[0] === 'word') this.readWord(tok[1], vid, scope, raw, findings);
    else findings.push(message('c4.unexpected-include-token', { view: vid, token: tok[1] }));
  }

  /** `*` or `* -> X`, past the `*`. */
  private readStar(vid: string, scope: Scope, raw: RawView, findings: string[]): void {
    if (this.cur()[0] !== 'arrow') {
      for (const eid of scope.topLevel) addBase(raw, eid);
      return;
    }
    this.advance();
    const next = this.advance();
    if (next[0] === 'star') findings.push(message('c4.star-to-star', { view: vid }));
    else if (next[0] !== 'word') findings.push(message('c4.malformed-predicate', { view: vid }));
    else if (this.anchorOk(scope, next[1], `* -> ${next[1]}`, findings)) raw.dstAnchors.add(next[1]);
  }

  /** `X`, `X -> *` or `X -> Y`, past the `X`. */
  private readWord(name: string, vid: string, scope: Scope, raw: RawView, findings: string[]): void {
    if (this.cur()[0] !== 'arrow') {
      if (scope.known.has(name)) addBase(raw, name);
      else findings.push(message('c4.view-includes-unknown', { view: vid, name }));
      return;
    }
    this.advance();
    const next = this.advance();
    if (next[0] === 'word') findings.push(message('c4.unsupported-predicate', { view: vid, src: name, dst: next[1] }));
    else if (next[0] !== 'star') findings.push(message('c4.malformed-predicate', { view: vid }));
    else if (this.anchorOk(scope, name, `${name} -> *`, findings)) raw.srcAnchors.add(name);
  }

  body(vid: string, scope: Scope, findings: string[]): RawView {
    const raw: RawView = { id: vid, title: '', root: scope.root, base: [], srcAnchors: new Set(), dstAnchors: new Set() };
    while (!['}', 'eof'].includes(this.cur()[0])) {
      const tok = this.advance();
      if (same(tok, ['word', 'title'])) {
        const st = this.advance();
        if (st[0] === 'str') raw.title = st[1];
        else findings.push(message('c4.title-not-string', { view: vid }));
      } else if (same(tok, ['word', 'include'])) {
        this.readSpec(vid, scope, raw, findings);
        while (this.cur()[0] === ',') {
          this.advance();
          this.readSpec(vid, scope, raw, findings);
        }
      } else findings.push(message('c4.unrecognized-directive', { view: vid, token: tok[1] }));
    }
    if (this.cur()[0] === '}') this.advance();
    return raw;
  }

  /** `view <id> [of <root>] {` as [id, root]; null (and a finding) when malformed. */
  header(): [string, string | null] | null {
    const parsed = this.rawHeader();
    if (parsed === null) this.findings.push(message('c4.malformed-view'));
    return parsed;
  }

  private rawHeader(): [string, string | null] | null {
    const idt = this.advance();
    if (idt[0] !== 'word') return null;
    const next = this.advance();
    if (same(next, ['word', 'of'])) {
      const scope = this.advance();
      return scope[0] === 'word' && this.advance()[0] === '{' ? [idt[1], scope[1]] : null;
    }
    return next[0] === '{' ? [idt[1], null] : null;
  }
}

export const EMPTY_VIEWS = 'views {\n}\n';

/** Parse `architecture/views.c4` (absent: an empty `views` block); the layout check guarantees its one block. */
export function parseViews(root: string, model: ModelParse): ViewsParse {
  const path = join(root, architecture().views_file);
  const isFile = existsSync(path) && statSync(path).isFile();
  const parser = new Parser(tokenize(isFile ? readFileSync(path, 'utf8') : EMPTY_VIEWS));
  const scopes = new Map(roots(model).map((r) => [r, scopeOf(model, r)]));
  const raw: RawView[] = [];
  const seenIds = new Set<string>();
  parser.pos = 2; // past `views {`
  while (!['}', 'eof'].includes(parser.cur()[0])) {
    if (!same(parser.advance(), ['word', 'view'])) parser.findings.push(message('c4.expected-view'));
    else {
      const header = parser.header();
      if (header !== null) readView(parser, header, scopes, model, raw, seenIds);
    }
  }
  const depths = viewDepths(root, seenIds, parser.findings);
  const views = raw.map((spec) =>
    buildView(spec, depths.get(spec.id) ?? DEFAULT_VIEW_DEPTH, scopes.get(spec.root)?.model ?? model),
  );
  return { views, findings: parser.findings };
}

/** A view's body past its header, kept in `raw` when it is scoped to a known root. */
function readView(
  parser: Parser,
  [vid, scopeId]: [string, string | null],
  scopes: Map<string, Scope>,
  model: ModelParse,
  raw: RawView[],
  seenIds: Set<string>,
): void {
  const scope = scopeId === null ? undefined : scopes.get(scopeId);
  if (scopeId === null) parser.findings.push(message('c4.view-unscoped', { view: vid }));
  else if (scope === undefined) parser.findings.push(message('c4.view-scope-unknown', { view: vid, root: scopeId }));
  if (scope !== undefined) raw.push(parser.body(vid, scope, parser.findings));
  else parser.body(vid, scopeOf(model, ''), []);
  if (seenIds.has(vid)) parser.findings.push(message('c4.duplicate-view', { view: vid }));
  seenIds.add(vid);
}

function isPositiveInt(value: unknown): value is number | bigint {
  if (typeof value === 'bigint') return value >= 1n;
  return typeof value === 'number' && Number.isInteger(value) && value >= 1;
}

/** Per-view render depth from index.yaml `view_depth`; malformed entries are findings, not errors. */
function viewDepths(root: string, validIds: Set<string>, findings: string[]): Map<string, number> {
  const index = readIndex(root);
  const depthMap = index instanceof Map ? index.get('view_depth') : undefined;
  const depths = new Map<string, number>();
  if (depthMap === undefined || depthMap === null) return depths;
  if (!(depthMap instanceof Map)) {
    findings.push(message('c4.view-depth-not-mapping'));
    return depths;
  }
  for (const [vid, value] of depthMap) {
    if (typeof vid !== 'string' || !validIds.has(vid)) {
      findings.push(message('c4.view-depth-unknown-view', { view: vid }));
    } else if (!isPositiveInt(value)) {
      findings.push(message('c4.view-depth-invalid', { view: vid, value }));
    } else depths.set(vid, Number(value));
  }
  return depths;
}

function childrenMap(model: ModelParse): Map<string, string[]> {
  const kids = new Map<string, string[]>();
  for (const e of model.elements) {
    if (e.parent !== null) kids.set(e.parent, [...(kids.get(e.parent) ?? []), e.id]);
  }
  return kids;
}

/** `eid` and every ancestor id, top-level first (`a.b.c` -> [a, a.b, a.b.c]). */
function ancestorChain(eid: string): string[] {
  const parts = eid.split('.');
  return parts.map((_, i) => parts.slice(0, i + 1).join('.'));
}

/** Pre-order ids of `root` and all its descendants (model declaration order within a parent). */
function subtree(root: string, kids: Map<string, string[]>): string[] {
  return [root, ...(kids.get(root) ?? []).flatMap((child) => subtree(child, kids))];
}

/** The deepest level a selection shows: `depth` levels counted from the selection itself. */
const reach = (selection: string, depth: number): number => level(selection) + depth - 1;

/** The predicate anchors matching `r`: a source anchor at or above its source, a target anchor at or above its target. */
function anchors(r: Relation, spec: RawView): string[] {
  return [...[...spec.srcAnchors].filter((a) => isOrAncestor(a, r.src)), ...[...spec.dstAnchors].filter((a) => isOrAncestor(a, r.dst))];
}

const inBase = (eid: string, spec: RawView): boolean => spec.base.some((selection) => isOrAncestor(selection, eid));

/** Both endpoints of `r` cut to the reach of each predicate anchor matching it, with their ancestors. */
function anchoredIds(r: Relation, spec: RawView, depth: number): string[] {
  return anchors(r, spec).flatMap((anchor) => {
    const limit = reach(anchor, depth);
    return [r.src, r.dst].flatMap((endpoint) => ancestorChain(ancestorAtLevel(endpoint, Math.min(limit, level(endpoint)))));
  });
}

/** Each include's subtree down to its reach, plus each predicate-matched endpoint cut to the anchor's reach, with its ancestors. */
function shownIds(spec: RawView, depth: number, model: ModelParse, kids: Map<string, string[]>): Set<string> {
  const shown = new Set<string>();
  for (const selection of spec.base) {
    const limit = reach(selection, depth);
    for (const eid of subtree(selection, kids)) if (level(eid) <= limit) shown.add(eid);
  }
  for (const r of model.relations) for (const eid of anchoredIds(r, spec, depth)) shown.add(eid);
  return shown;
}

/** The nearest shown ancestor of `eid` (itself if shown), or null. */
function represent(eid: string, shown: Set<string>): string | null {
  return [...ancestorChain(eid)].reverse().find((anc) => shown.has(anc)) ?? null;
}

/** Relations projected onto shown representatives, deduped in first-seen order; legacy iff every contributor is. */
function viewEdges(model: ModelParse, spec: RawView, shown: Set<string>): Edge[] {
  const contributors = new Map<string, { src: string; dst: string; legacy: boolean[] }>();
  for (const r of model.relations) {
    if (!((inBase(r.src, spec) && inBase(r.dst, spec)) || anchors(r, spec).length > 0)) continue;
    const [src, dst] = [represent(r.src, shown), represent(r.dst, shown)];
    if (src === null || dst === null || src === dst) continue;
    const key = `${src}\0${dst}`;
    const entry = contributors.get(key) ?? { src, dst, legacy: [] };
    entry.legacy.push(r.legacy);
    contributors.set(key, entry);
  }
  return [...contributors.values()].map((e) => ({ src: e.src, dst: e.dst, legacy: e.legacy.every(Boolean) }));
}

/** Expand includes to their reach; predicate pulls add only the matched endpoints and their ancestor chains. */
function buildView(spec: RawView, depth: number, model: ModelParse): View {
  const shown = shownIds(spec, depth, model, childrenMap(model));
  const edges = viewEdges(model, spec, shown);
  const nodeIds = model.elements.filter((e) => shown.has(e.id)).map((e) => e.id);
  return { id: spec.id, title: spec.title, root: spec.root, nodeIds, edges };
}
