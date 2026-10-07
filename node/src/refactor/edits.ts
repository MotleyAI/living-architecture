// A refactor's change set: text edits merged across projects, validated, then applied.
import { message } from '../contract/index.js';

/** The refactor cannot be computed or applied; the message is user-facing, exit 1. */
export class RefactorError extends Error {}

/** One text edit of a file, in UTF-16 offsets of its current text. */
export interface Edit {
  path: string;
  start: number;
  length: number;
  newText: string;
}

const end = (edit: Edit): number => edit.start + edit.length;

/** Each file's edits in offset order (ties keep input order), identical ones once; RefactorError when two collide. */
export function mergeEdits(edits: Edit[]): Map<string, Edit[]> {
  const byPath = new Map<string, Edit[]>();
  for (const edit of edits) {
    const kept = byPath.get(edit.path) ?? [];
    const same = kept.find((e) => e.start === edit.start && e.length === edit.length);
    if (same?.newText === edit.newText) continue;
    const collides = (e: Edit): boolean => e.start < end(edit) && edit.start < end(e);
    if (same !== undefined || kept.some(collides)) throw new RefactorError(message('refactor.conflicting-edits', { path: edit.path }));
    byPath.set(edit.path, [...kept, edit]);
  }
  for (const kept of byPath.values()) kept.sort((a, b) => a.start - b.start);
  return byPath;
}

/** `text` with `edits` (offset order, as mergeEdits returns them) applied. */
export function applyEdits(text: string, edits: Edit[]): string {
  let out = text;
  for (const edit of [...edits].reverse()) out = out.slice(0, edit.start) + edit.newText + out.slice(end(edit));
  return out;
}
