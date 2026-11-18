// `PATH[:LINE]` sites of `rename --keep`, `--with`, `--without` and `--docs-pick`, the keep text check, and the
// literals of `--keep-literal`.
import { existsSync, realpathSync, statSync } from 'node:fs';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import { message, readFile } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { identifierText } from './bindings.js';
import { Lines } from './lines.js';
import { walk } from './members.js';
import { sourceRegions } from './mentions.js';
import { type Refusal, refusal } from './progress.js';

/** A site as given, its real path's components under the project (null outside it or missing) and its line. */
export class Site {
  private constructor(
    readonly raw: string,
    readonly parts: string[] | null,
    readonly line: number | null,
  ) {}

  /** `raw` with its path resolved against the project `root`. */
  static parse(raw: string, root: string): Site {
    const m = /^(.*):(\d+)$/u.exec(raw);
    const path = m === null ? raw : (m[1] ?? '');
    const line = m === null ? null : Number(m[2]);
    const absolute = resolve(root, path);
    if (!existsSync(absolute)) return new Site(raw, null, line);
    const rel = relative(root, realpathSync(absolute));
    const inside = !isAbsolute(rel) && rel.split(sep)[0] !== '..';
    return new Site(raw, inside ? rel.split(sep).filter((p) => p !== '') : null, line);
  }

  /** `rel:line` is this site: the same line of the file, or anywhere in the file or under the directory. */
  covers(rel: string, line: number): boolean {
    return this.coversPath(rel) && (this.line === null || this.line === line);
  }

  /** `rel` is this site's file or under its directory. */
  coversPath(rel: string): boolean {
    if (this.parts === null) return false;
    const path = rel.split('/');
    return this.parts.every((part, i) => path[i] === part);
  }

  /** The site names no file or directory under `root`, or a line its file does not have. */
  missing(root: string): boolean {
    if (this.parts === null || this.line === null) return this.parts === null;
    const path = join(root, ...this.parts);
    if (!statSync(path).isFile()) return true;
    const count = new Lines(readFile(path, 'utf8')).count;
    return this.line < 1 || this.line > count;
  }
}

/** A `--docs-pick` as given: its line site and the entry it names. */
export class Pick {
  private constructor(
    readonly raw: string,
    readonly site: Site,
    readonly entry: number | null,
  ) {}

  static parse(raw: string, root: string): Pick {
    const m = /^(.*:\d+)=(\d+)$/u.exec(raw);
    return new Pick(raw, Site.parse(m === null ? raw : (m[1] ?? ''), root), m === null ? null : Number(m[2]));
  }

  /** The pick names no line of a file under `root`. */
  missing(root: string): boolean {
    return this.site.line === null || this.site.missing(root);
  }
}

/** The span of an object literal holding one of `keys`, with the indexes of the keys it holds. */
export interface LiteralSpan {
  start: number;
  end: number;
  held: number[];
}

/** The index in `keys` of the name an object literal member is written by: an identifier, a string literal's text
 * between its quotes, or a shorthand property. */
function heldKey(member: TS.ObjectLiteralElementLike, source: TS.SourceFile, keys: string[]): number {
  const name = member.name;
  if (name === undefined) return -1;
  if (ts().isIdentifier(name)) return keys.indexOf(name.text);
  return ts().isStringLiteral(name) ? keys.indexOf(name.getText(source).slice(1, -1)) : -1;
}

/** Each object literal of `source` holding a property named by one of `keys`. */
export function literalSpans(source: TS.SourceFile, keys: string[]): LiteralSpan[] {
  const out: LiteralSpan[] = [];
  for (const node of walk(source)) {
    if (!ts().isObjectLiteralExpression(node)) continue;
    const held = node.properties.map((member) => heldKey(member, source, keys)).filter((i) => i >= 0);
    if (held.length > 0) out.push({ start: node.getStart(source), end: node.end, held });
  }
  return out;
}

/** `--keep-literal` keys: the literals they keep in each file (`spans`), and the keys that kept nothing. */
export class LiteralKeeps {
  readonly keys: string[];
  private readonly files = new Map<string, LiteralSpan[]>();
  private readonly matched = new Set<number>();

  constructor(
    keys: string[],
    private readonly spans: (path: string, keys: string[]) => LiteralSpan[],
  ) {
    this.keys = [...new Set(keys)];
  }

  /** `start`..`end` of `path` overlaps a kept literal; `mark` counts the keys keeping it. */
  kept(path: string, start: number, end: number, mark = true): boolean {
    if (this.keys.length === 0) return false;
    let spans = this.files.get(path);
    if (spans === undefined) {
      spans = this.spans(path, this.keys);
      this.files.set(path, spans);
    }
    const hits = spans.filter((span) => span.start < end && start < span.end);
    if (mark) for (const span of hits) for (const i of span.held) this.matched.add(i);
    return hits.length > 0;
  }

  /** A `refactor.keep-literal-unneeded` warning for each key that kept nothing, in command-line order. */
  unneeded(): string[] {
    return this.keys.filter((_, i) => !this.matched.has(i)).map((key) => message('refactor.keep-literal-unneeded', { key }));
  }
}

/** `text` with every comment of `source` blanked, its line breaks kept. */
function uncommented(text: string, source: TS.SourceFile): string {
  let out = text;
  for (const region of sourceRegions(source)) {
    if (region.where !== 'comment') continue;
    const blank = out.slice(region.start, region.end).replace(/[^\r\n\u2028\u2029]/gu, (c) => ' '.repeat(c.length));
    out = out.slice(0, region.start) + blank + out.slice(region.end);
  }
  return out;
}

/** The 1-based lines of `text` spelling one of `names` as written (unicode escapes decoded) or, in `code`, in the value
 * of a string or template literal starting on the line; without `comments`, not in a code comment. `file` names the
 * source, its extension setting how it parses. */
export function spelledLines(text: string, names: Set<string>, code = true, comments = true, file = 'keep.ts'): Set<number> {
  const source = code ? ts().createSourceFile(file, text, ts().ScriptTarget.Latest, true) : null;
  const lines = new Lines(source === null || comments ? text : uncommented(text, source));
  const out = new Set<number>();
  const decoded = [...names].map((name) => identifierText(name));
  const spells = (value: string): boolean => decoded.some((name) => value.includes(name));
  for (let line = 1; line <= lines.count; line += 1) if (spells(identifierText(lines.lineText(line)))) out.add(line);
  if (source === null) return out;
  const visit = (node: TS.Node): void => {
    const literal = ts().isStringLiteralLike(node) || ts().isTemplateHead(node) || ts().isTemplateMiddle(node) || ts().isTemplateTail(node);
    if (literal && spells((node as TS.LiteralLikeNode).text)) out.add(lines.lineOf(node.getStart(source)));
    ts().forEachChild(node, visit);
  };
  visit(source);
  return out;
}

/** `site` covers a file the refactor moves, or a line of an `editable` file (its value: a source, else prose) spelling
 * one of `names` (in a comment only with `comments`). */
export function keepSpells(site: Site, editable: Map<string, boolean>, text: (rel: string) => string, names: Set<string>, moved: string[], comments = true): boolean {
  const parts = site.parts;
  if (parts === null) return false;
  if (moved.some((rel) => site.coversPath(rel) || rel.split('/').every((part, i) => parts[i] === part))) return true;
  for (const [rel, isCode] of editable) {
    if (!site.coversPath(rel)) continue;
    const lines = spelledLines(text(rel), names, isCode, comments, rel);
    if (lines.size > 0 && (site.line === null || lines.has(site.line))) return true;
  }
  return false;
}

/** The line of `edited` nearest to `line`, the earlier of two equally near; null when there is none. */
export function nearestLine(edited: Iterable<number>, line: number): number | null {
  let best: number | null = null;
  for (const e of edited) {
    const closer = best === null || Math.abs(e - line) < Math.abs(best - line) || (Math.abs(e - line) === Math.abs(best - line) && e < best);
    if (closer) best = e;
  }
  return best;
}

/** Each keep of `unmatched`: a `refactor.keep-unneeded` warning for a whole-path keep, a refusal naming the nearest of
 * its file's `edited` lines for a line keep. */
export function resolveKeeps(unmatched: Site[], edited: Map<string, number[]>): { warnings: string[]; refusals: Refusal[] } {
  const warnings: string[] = [];
  const refusals: Refusal[] = [];
  for (const site of unmatched) {
    if (site.line === null) {
      warnings.push(message('refactor.keep-unneeded', { site: site.raw }));
      continue;
    }
    const rel = (site.parts ?? []).join('/');
    const near = nearestLine(edited.get(rel) ?? [], site.line);
    const text =
      near === null
        ? message('refactor.keep-unmatched', { site: site.raw })
        : message('refactor.keep-unmatched-near', { site: site.raw, path: rel, line: near });
    refusals.push(refusal(text, 2));
  }
  return { warnings, refusals };
}
