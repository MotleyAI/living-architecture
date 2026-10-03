// The constrained `views.c4` include grammar and view expansion over a root-local projection.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isWordStart, message, splitLines } from '../contract/index.js';
import { readIndex } from './index-file.js';
import { type ModelParse, project, roots, stripLineComment } from './model.js';

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

const top = (eid: string): string => eid.split('.')[0] ?? eid;
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
  private pos = 0;
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
    if (!scope.topLevel.includes(name)) {
      findings.push(message('c4.include-non-top-level', { form, name }));
      return false;
    }
    return true;
  }

  private readSpec(vid: string, scope: Scope, raw: RawView, findings: string[]): void {
    const tok = this.advance();
    if (tok[0] === 'star') {
      if (this.cur()[0] === 'arrow') {
        this.advance();
        const next = this.advance();
        if (next[0] === 'star') findings.push(message('c4.star-to-star', { view: vid }));
        else if (next[0] === 'word') {
          if (this.anchorOk(scope, next[1], `* -> ${next[1]}`, findings)) raw.dstAnchors.add(next[1]);
        } else findings.push(message('c4.malformed-predicate', { view: vid }));
      } else {
        for (const eid of scope.topLevel) addBase(raw, eid);
      }
    } else if (tok[0] === 'word') {
      if (this.cur()[0] === 'arrow') {
        this.advance();
        const next = this.advance();
        if (next[0] === 'star') {
          if (this.anchorOk(scope, tok[1], `${tok[1]} -> *`, findings)) raw.srcAnchors.add(tok[1]);
        } else if (next[0] === 'word') {
          findings.push(message('c4.unsupported-predicate', { view: vid, src: tok[1], dst: next[1] }));
        } else findings.push(message('c4.malformed-predicate', { view: vid }));
      } else if (!scope.known.has(tok[1])) {
        findings.push(message('c4.view-includes-unknown', { view: vid, name: tok[1] }));
      } else if (!scope.topLevel.includes(tok[1])) {
        findings.push(message('c4.view-includes-non-top-level', { view: vid, name: tok[1] }));
      } else addBase(raw, tok[1]);
    } else {
      findings.push(message('c4.unexpected-include-token', { view: vid, token: tok[1] }));
    }
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
    const idt = this.advance();
    if (idt[0] !== 'word') {
      this.findings.push(message('c4.malformed-view'));
      return null;
    }
    const next = this.advance();
    if (same(next, ['word', 'of'])) {
      const scope = this.advance();
      if (scope[0] !== 'word' || this.advance()[0] !== '{') {
        this.findings.push(message('c4.malformed-view'));
        return null;
      }
      return [idt[1], scope[1]];
    }
    if (next[0] !== '{') {
      this.findings.push(message('c4.malformed-view'));
      return null;
    }
    return [idt[1], null];
  }
}

/** Parse `architecture/views.c4`: views scoped to a language root, includes relative to it. */
export function parseViews(root: string, model: ModelParse): ViewsParse {
  const path = join(root, 'architecture', 'views.c4');
  if (!existsSync(path)) return { views: [], findings: [] };
  const parser = new Parser(tokenize(readFileSync(path, 'utf8')));
  const scopes = new Map(roots(model).map((r) => [r, scopeOf(model, r)]));
  const raw: RawView[] = [];
  const seenIds = new Set<string>();
  if (!same(parser.advance(), ['word', 'views']) || parser.advance()[0] !== '{') {
    parser.findings.push(message('c4.no-views-block'));
    return { views: [], findings: parser.findings };
  }
  while (!['}', 'eof'].includes(parser.cur()[0])) {
    if (!same(parser.advance(), ['word', 'view'])) {
      parser.findings.push(message('c4.expected-view'));
      continue;
    }
    const header = parser.header();
    if (header === null) continue;
    const [vid, scopeId] = header;
    const scope = scopeId === null ? undefined : scopes.get(scopeId);
    if (scopeId === null) parser.findings.push(message('c4.view-unscoped', { view: vid }));
    else if (scope === undefined) parser.findings.push(message('c4.view-scope-unknown', { view: vid, root: scopeId }));
    if (scope !== undefined) raw.push(parser.body(vid, scope, parser.findings));
    else parser.body(vid, scopeOf(model, ''), []);
    if (seenIds.has(vid)) parser.findings.push(message('c4.duplicate-view', { view: vid }));
    seenIds.add(vid);
  }
  const depths = viewDepths(root, seenIds, parser.findings);
  const views = raw.map((spec) =>
    buildView(spec, depths.get(spec.id) ?? DEFAULT_VIEW_DEPTH, scopes.get(spec.root)?.model ?? model),
  );
  return { views, findings: parser.findings };
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

/** Each base's subtree down to `depth`, plus every predicate-matched endpoint collapsed to `depth` and its ancestors. */
function shownIds(spec: RawView, depth: number, model: ModelParse, kids: Map<string, string[]>): Set<string> {
  const shown = new Set<string>();
  for (const base of spec.base) {
    for (const eid of subtree(base, kids)) if (level(eid) <= depth) shown.add(eid);
  }
  for (const r of model.relations) {
    if (!spec.srcAnchors.has(top(r.src)) && !spec.dstAnchors.has(top(r.dst))) continue;
    for (const endpoint of [r.src, r.dst]) {
      for (const anc of ancestorChain(ancestorAtLevel(endpoint, Math.min(depth, level(endpoint))))) shown.add(anc);
    }
  }
  return shown;
}

/** The nearest shown ancestor of `eid` (itself if shown), or null. */
function represent(eid: string, shown: Set<string>): string | null {
  return [...ancestorChain(eid)].reverse().find((anc) => shown.has(anc)) ?? null;
}

/** Relations projected onto shown representatives, deduped in first-seen order; legacy iff every contributor is. */
function viewEdges(model: ModelParse, spec: RawView, among: Set<string>, shown: Set<string>): Edge[] {
  const contributors = new Map<string, { src: string; dst: string; legacy: boolean[] }>();
  for (const r of model.relations) {
    const inView =
      (among.has(top(r.src)) && among.has(top(r.dst))) || spec.srcAnchors.has(top(r.src)) || spec.dstAnchors.has(top(r.dst));
    if (!inView) continue;
    const [src, dst] = [represent(r.src, shown), represent(r.dst, shown)];
    if (src === null || dst === null || src === dst) continue;
    const key = `${src}\0${dst}`;
    const entry = contributors.get(key) ?? { src, dst, legacy: [] };
    entry.legacy.push(r.legacy);
    contributors.set(key, entry);
  }
  return [...contributors.values()].map((e) => ({ src: e.src, dst: e.dst, legacy: e.legacy.every(Boolean) }));
}

/** Expand base includes to `depth`; predicate pulls add only the matched endpoint and its ancestor chain. */
function buildView(spec: RawView, depth: number, model: ModelParse): View {
  const shown = shownIds(spec, depth, model, childrenMap(model));
  const edges = viewEdges(model, spec, new Set(spec.base), shown);
  const nodeIds = model.elements.filter((e) => shown.has(e.id)).map((e) => e.id);
  return { id: spec.id, title: spec.title, root: spec.root, nodeIds, edges };
}
