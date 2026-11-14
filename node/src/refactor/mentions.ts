// `rename --docs`: the old name's mentions in comments, strings, template text and prose files, rewritten when
// qualified or code-marked, else listed.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import { walk } from './members.js';

/** A comment, string literal content or prose text, and whether it opens a string literal. */
export interface Region {
  start: number;
  end: number;
  where: 'comment' | 'string' | 'prose';
  opens: boolean;
}

/** A renamed declaration's qualifying path (module segments, then classes) and whether a class declares it. */
export interface Owner {
  path: string[];
  member: boolean;
}

export interface Mention {
  start: number;
  end: number;
  where: Region['where'];
  opens: boolean;
}

const QUALIFIER = /((?:[A-Za-z_$][\w$]*[.#])*[A-Za-z_$][\w$]*)[.#]$/u;
const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');

/** The comments, string contents and template-literal text of a TypeScript file. */
export function sourceRegions(source: TS.SourceFile): Region[] {
  const text = source.text;
  const out: Region[] = [];
  const seen = new Set<number>();
  const comment = (ranges: TS.CommentRange[] | undefined): void => {
    for (const r of ranges ?? []) {
      if (seen.has(r.pos)) continue;
      seen.add(r.pos);
      out.push({ start: r.pos, end: r.end, where: 'comment', opens: false });
    }
  };
  const k = ts().SyntaxKind;
  for (const node of walk(source)) {
    comment(ts().getLeadingCommentRanges(text, node.pos));
    comment(ts().getTrailingCommentRanges(text, node.end));
    const start = node.kind === k.EndOfFileToken ? -1 : node.getStart(source);
    if (node.kind === k.StringLiteral || node.kind === k.NoSubstitutionTemplateLiteral) {
      out.push({ start: start + 1, end: node.end - 1, where: 'string', opens: true });
    } else if (node.kind === k.TemplateHead) {
      out.push({ start: start + 1, end: node.end - 2, where: 'string', opens: true });
    } else if (node.kind === k.TemplateMiddle) {
      out.push({ start: start + 1, end: node.end - 2, where: 'string', opens: false });
    } else if (node.kind === k.TemplateTail) {
      out.push({ start: start + 1, end: node.end - 1, where: 'string', opens: false });
    }
  }
  return out;
}

/** Occurrences of `old` not adjacent to an identifier character inside each region. */
export function mentions(text: string, old: string, regions: Region[]): Mention[] {
  const pattern = new RegExp(`(?<![\\w$])${escape(old)}(?![\\w$])`, 'gu');
  const out: Mention[] = [];
  for (const region of regions) {
    pattern.lastIndex = region.start;
    for (let m = pattern.exec(text); m !== null && m.index + old.length <= region.end; m = pattern.exec(text)) {
      out.push({ start: m.index, end: m.index + old.length, where: region.where, opens: region.opens && m.index === region.start });
    }
  }
  return out;
}

/** `Owner.OLD` or `Owner#OLD`, with an optional dotted prefix naming the owner's module from its end. */
export function qualified(text: string, start: number, owners: Owner[], colliding: Set<string>): boolean {
  const m = QUALIFIER.exec(text.slice(Math.max(0, start - 300), start));
  if (m === null) return false;
  const before = text[start - m[0].length - 1] ?? '';
  if (/[\w$.#]/u.test(before)) return false;
  const segments = (m[1] ?? '').split(/[.#]/u);
  const bare = segments.length === 1 ? segments[0] : undefined;
  return owners.some((owner) => {
    const tail = owner.path.slice(owner.path.length - segments.length);
    if (segments.length > owner.path.length || tail.join('.') !== segments.join('.')) return false;
    return bare === undefined || !owner.member || !colliding.has(bare);
  });
}

/** In backticks (optionally followed by `()`), a `{@link}` or role target, or opening its string before `:`, `(` or
 * whitespace. */
export function codeMarked(text: string, mention: Mention): boolean {
  const before = text.slice(Math.max(0, mention.start - 20), mention.start);
  const after = text.slice(mention.end, mention.end + 3);
  if (/`[~!]?$/u.test(before) && (after.startsWith('`') || after.startsWith('()`'))) return true;
  if (/\{@link\s+$/u.test(before) && /^[}\s|]/u.test(after)) return true;
  return mention.opens && /^[:(\s]/u.test(after);
}
