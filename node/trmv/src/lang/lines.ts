// Line map and comment line sets of a decoded source: breaks are `\r\n`, `\n` and `\r` only.
import type * as TS from 'typescript';
import { ts } from './ts.js';

export class LineMap {
  /** Start offset of every line; a trailing break opens no extra line. */
  readonly starts: number[] = [];

  constructor(readonly text: string) {
    if (text === '') return;
    this.starts.push(0);
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (ch === '\r' && text[i + 1] === '\n') i++;
      else if (ch !== '\r' && ch !== '\n') continue;
      if (i + 1 < text.length) this.starts.push(i + 1);
    }
  }

  get count(): number {
    return this.starts.length;
  }

  /** 1-based line of offset `pos`. */
  lineOf(pos: number): number {
    let lo = 0;
    let hi = this.starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if ((this.starts[mid] ?? 0) <= pos) lo = mid;
      else hi = mid - 1;
    }
    return lo + 1;
  }

  /** The text of 1-based `line`, without its break. */
  lineText(line: number): string {
    const start = this.starts[line - 1] ?? this.text.length;
    const end = this.starts[line] ?? this.text.length;
    return this.text.slice(start, end).replace(/(?:\r\n|\r|\n)$/, '');
  }
}

/** Every comment range of `file` (shebang excluded, JSX text never scanned), in source order. */
export function commentRanges(file: TS.SourceFile): TS.CommentRange[] {
  const text = file.text;
  const found = new Map<number, TS.CommentRange>();
  const positions = new Set<number>();
  const visit = (node: TS.Node): void => {
    if (node.kind === ts().SyntaxKind.JsxText) return;
    positions.add(node.pos);
    for (const child of node.getChildren(file)) visit(child);
  };
  visit(file);
  for (const pos of positions) {
    const leading = ts().getLeadingCommentRanges(text, pos) ?? [];
    const trailing = ts().getTrailingCommentRanges(text, pos) ?? [];
    for (const range of [...leading, ...trailing]) found.set(range.pos, range);
  }
  return [...found.values()].sort((a, b) => a.pos - b.pos);
}

export interface LineCounts {
  text_lines: number;
  comment_lines: number;
  doc_lines: number;
}

const isDoc = (text: string, range: TS.CommentRange): boolean =>
  text.startsWith('/**', range.pos) && text.slice(range.pos, range.end) !== '/**/';

/** Text-only lines (comment text and whitespace only), and distinct comment and doc lines. */
export function lineCounts(lines: LineMap, ranges: TS.CommentRange[]): LineCounts {
  const text = lines.text;
  const covered = new Uint8Array(text.length);
  const comment = new Set<number>();
  const doc = new Set<number>();
  for (const range of ranges) {
    covered.fill(1, range.pos, range.end);
    const set = isDoc(text, range) ? doc : comment;
    for (let line = lines.lineOf(range.pos); line <= lines.lineOf(range.end - 1); line++) set.add(line);
  }
  let textLines = 0;
  for (let line = 1; line <= lines.count; line++) {
    const start = lines.starts[line - 1] ?? 0;
    const end = lines.starts[line] ?? text.length;
    let any = false;
    let code = false;
    for (let i = start; i < end && !code; i++) {
      if (/\s/u.test(text[i] ?? '')) continue;
      if (covered[i]) any = true;
      else code = true;
    }
    if (any && !code) textLines++;
  }
  return { text_lines: textLines, comment_lines: comment.size, doc_lines: doc.size };
}
