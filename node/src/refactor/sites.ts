// `PATH[:LINE]` sites of `rename --keep`, `--with` and `--without`, and the keep text check.
import { existsSync, realpathSync, statSync } from 'node:fs';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import { message, readFile } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { identifierText } from './bindings.js';
import { Lines } from './lines.js';
import { sourceRegions } from './mentions.js';
import { type Refusal, refusal } from './progress.js';

/** A site as given, its real path's components under the project (null outside it or missing) and its line. */
export class Site {
  private constructor(
    readonly raw: string,
    readonly parts: string[] | null,
    readonly line: number | null,
  ) {}

  /** `raw` with its path resolved against `base` (the working directory by default). */
  static parse(raw: string, root: string, base: string = process.cwd()): Site {
    const m = /^(.*):(\d+)$/u.exec(raw);
    const path = m === null ? raw : (m[1] ?? '');
    const line = m === null ? null : Number(m[2]);
    const absolute = resolve(base, path);
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
