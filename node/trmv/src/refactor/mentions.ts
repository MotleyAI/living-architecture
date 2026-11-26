// `rename --docs`: the old name's mentions in comments, strings, template text and prose files, and what marks one as
// qualified or as code.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import { walk } from './members.js';

/** A comment, string literal content or prose text. */
export interface Region {
  start: number;
  end: number;
  where: 'comment' | 'string' | 'prose';
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
}

// Identifier-continuation characters: Unicode's, the zero-width joiners and `$`.
const WORD = String.raw`(?:[\p{ID_Continue}$]|\u200C|\u200D)`;
const QUALIFIER_CHAR = new RegExp(`^(?:${WORD}|[.#])$`, 'u');
const IDENTIFIER = new RegExp(`^[A-Za-z_$]${WORD}*$`, 'u');
const QUALIFIER_WINDOW = 300;
const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/gu, String.raw`\$&`);

/** The code point ending at UTF-16 offset `end` of `text`, or '' at the start. */
function charBefore(text: string, end: number): string {
  if (end <= 0) return '';
  const pair = end >= 2 ? text.slice(end - 2, end) : '';
  return pair.length === 2 && [...pair].length === 1 ? pair : text.slice(end - 1, end);
}

/** The segments of the `A.B.` or `A#` qualifier ending at `start`, or null when the run there is not one. */
export function qualifierSegments(text: string, start: number): string[] | null {
  let i = start;
  let chars = 0;
  for (let c = charBefore(text, i); chars < QUALIFIER_WINDOW && QUALIFIER_CHAR.test(c); c = charBefore(text, i)) {
    i -= c.length;
    chars++;
  }
  if (QUALIFIER_CHAR.test(charBefore(text, i))) return null;
  const segments = text.slice(i, start).split(/[.#]/u);
  if (segments.pop() !== '' || segments.length === 0) return null;
  return segments.every((s) => IDENTIFIER.test(s)) ? segments : null;
}

/** The comments, string contents and template-literal text of a TypeScript file. */
export function sourceRegions(source: TS.SourceFile): Region[] {
  const text = source.text;
  const out: Region[] = [];
  const seen = new Set<number>();
  const comment = (ranges: TS.CommentRange[] | undefined): void => {
    for (const r of ranges ?? []) {
      if (seen.has(r.pos)) continue;
      seen.add(r.pos);
      out.push({ start: r.pos, end: r.end, where: 'comment' });
    }
  };
  const k = ts().SyntaxKind;
  for (const node of walk(source)) {
    comment(ts().getLeadingCommentRanges(text, node.pos));
    comment(ts().getTrailingCommentRanges(text, node.end));
    const start = node.kind === k.EndOfFileToken ? -1 : node.getStart(source);
    if (node.kind === k.StringLiteral || node.kind === k.NoSubstitutionTemplateLiteral) {
      out.push({ start: start + 1, end: node.end - 1, where: 'string' });
    } else if (node.kind === k.TemplateHead || node.kind === k.TemplateMiddle) {
      out.push({ start: start + 1, end: node.end - 2, where: 'string' });
    } else if (node.kind === k.TemplateTail) {
      out.push({ start: start + 1, end: node.end - 1, where: 'string' });
    }
  }
  return out;
}

/** Occurrences of `old` not adjacent to an identifier character inside each region; a region ends the text. */
export function mentions(text: string, old: string, regions: Region[]): Mention[] {
  const pattern = new RegExp(`(?<!${WORD})${escape(old)}(?!${WORD})`, 'gu');
  const out: Mention[] = [];
  for (const region of regions) {
    const upToEnd = text.slice(0, region.end);
    pattern.lastIndex = region.start;
    for (let m = pattern.exec(upToEnd); m !== null; m = pattern.exec(upToEnd)) {
      out.push({ start: m.index, end: m.index + old.length, where: region.where });
    }
  }
  return out;
}

/** Whether `path` ends with `segments`. */
const endsWith = (path: string[], segments: string[]): boolean =>
  segments.length <= path.length && path.slice(path.length - segments.length).join('.') === segments.join('.');

/** `Owner.OLD` or `Owner#OLD`, with an optional dotted prefix naming the owner's module from its end, naming no
 * `colliding` class (the qualifying paths of other classes declaring OLD). */
export function qualified(text: string, start: number, owners: Owner[], colliding: string[][]): boolean {
  const segments = qualifierSegments(text, start);
  if (segments === null) return false;
  const ambiguous = colliding.some((path) => endsWith(path, segments));
  return owners.some((owner) => endsWith(owner.path, segments) && (!owner.member || !ambiguous));
}

/** In backticks (optionally followed by `()`), or a `{@link}` or role target. */
export function codeMarked(text: string, mention: Mention): boolean {
  const before = text.slice(Math.max(0, mention.start - 20), mention.start);
  const after = text.slice(mention.end, mention.end + 3);
  if (/`[~!]?$/u.test(before) && (after.startsWith('`') || after.startsWith('()`'))) return true;
  return /\{@link\s+$/u.test(before) && /^[}\s|]/u.test(after);
}
