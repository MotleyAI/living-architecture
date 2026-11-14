// Positions mapped through a refactor's edits, moved files and moved declarations, for the type-check baseline.
import type { Edit } from './edits.js';

/** A replaced span `[start, end)` and the length of its new text. */
export type Replaced = [start: number, end: number, length: number];

/** `start..end` after `edits` (sorted, disjoint): a start inside a replaced span maps to the replacement's start,
 * an end inside one to its end. */
export function mapRange(edits: Replaced[], start: number, end: number): [number, number] {
  let [newStart, newEnd, shift] = [start, end, 0];
  for (const [s, e, length] of edits) {
    if (s <= start && start < e) newStart = s + shift;
    else if (start >= e) newStart = start + shift + length - (e - s);
    if (s < end && end <= e) newEnd = s + shift + length;
    else if (end > e) newEnd = end + shift + length - (e - s);
    shift += length - (e - s);
  }
  return [newStart, newEnd];
}

/** A declaration moved from `start..end` of `from` into the text an edit inserts at `at` of `to`. */
export interface MovedSpan {
  from: string;
  start: number;
  end: number;
  to: string;
  at: number;
  /** The moved text's offset inside the inserted text, by offset inside the span; null where the move rewrote it. */
  offset: (inside: number) => number | null;
}

/** Where a refactor puts each position: per-file edits, moved files (old path to new) and moved declarations. */
export interface PositionMap {
  edits: Map<string, Edit[]>;
  moves: Map<string, string>;
  spans: MovedSpan[];
}

const replaced = (edits: Edit[]): Replaced[] => edits.map((e) => [e.start, e.start + e.length, e.newText.length]);

/** The file and start a position of `file` moves to; null when the refactor rewrote the text around it. */
export function mapPosition(map: PositionMap, file: string, position: number): { file: string; position: number } | null {
  const span = map.spans.find((s) => s.from === file && s.start <= position && position < s.end);
  if (span !== undefined) {
    const inside = span.offset(position - span.start);
    if (inside === null) return null;
    const before = replaced((map.edits.get(span.to) ?? []).filter((e) => e.start + e.length <= span.at && !(e.start === span.at && e.length === 0)));
    const [at] = mapRange(before, span.at, span.at);
    return { file: map.moves.get(span.to) ?? span.to, position: at + inside };
  }
  const [start] = mapRange(replaced(map.edits.get(file) ?? []), position, position);
  return { file: map.moves.get(file) ?? file, position: start };
}

/** The offsets of `text`'s characters other than white space. */
const inked = (text: string): number[] => [...text.matchAll(/\S/gu)].map((m) => m.index);

/** How offsets inside `moved` map into `inserted`, the text holding it: character by character, white space apart;
 * null for every offset when the move rewrote more than white space. */
export function movedOffsets(moved: string, inserted: string): (inside: number) => number | null {
  const [from, to] = [inked(moved), inked(inserted)];
  const squeezed = (text: string, offsets: number[]): string => offsets.map((o) => text[o]).join('');
  const at = squeezed(inserted, to).indexOf(squeezed(moved, from));
  return (inside) => {
    const rank = from.findIndex((offset) => offset >= inside);
    return at < 0 || rank < 0 ? null : (to[at + rank] ?? null);
  };
}
