// A rename rule's decision on each site it examines: rewrite, blind spot, leftover or unrelated, never none.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import type { Edit } from './edits.js';
import type { LiteralSource } from './literal-sources.js';
import { blindspotFinding, type FormCall, walk } from './members.js';
import type { Mention } from './mentions.js';

/** A line to print, as its template, the position it sits at and its values other than path and line. */
export interface PendingFinding {
  template: string;
  position: number;
  values: Record<string, unknown>;
}

/** One examined site (`start`..`end` of `path`) and what its rule decided. */
export interface Outcome {
  kind: 'rewrite' | 'blindspot' | 'leftover' | 'unrelated';
  path: string;
  start: number;
  end: number;
  edits: Edit[];
  finding?: PendingFinding;
}

const rewrite = (path: string, start: number, end: number, newText: string): Outcome => ({
  kind: 'rewrite',
  path,
  start,
  end,
  edits: [{ path, start, length: end - start, newText }],
});

/** A use landing on renamed and unchanged declarations: a mixed-target blind spot at `position`. */
export function mixedOutcome(path: string, start: number, end: number, position: number, receiver: string, old: string): Outcome {
  return { kind: 'blindspot', path, start, end, edits: [], finding: { template: 'refactor.mixed-target', position, values: { receiver, attr: old } } };
}

/** A typed member form whose lookup lands on declarations (`renamed`: whether each is renamed): rewritten when all
 * are, unrelated when none is, else a mixed-target blind spot. */
export function formCallOutcome(path: string, found: FormCall, renamed: boolean[], receiver: string, old: string, newName: string): Outcome {
  if (!renamed.includes(true)) return { kind: 'unrelated', path, start: found.start, end: found.end, edits: [] };
  if (!renamed.includes(false)) return rewrite(path, found.start, found.end, newName);
  return mixedOutcome(path, found.start, found.end, found.call.getStart(found.call.getSourceFile()), receiver, old);
}

/** An `any` receiver of the name: its access, or a string-named access (`named`) with its literal (`literal`). */
export function blindspotOutcome(
  path: string,
  position: number,
  literal: [number, number] | null,
  receiver: string,
  old: string,
  named: { site: string; silent?: boolean } | null = null,
): Outcome {
  const [start, end] = literal ?? [position, position];
  const finding = { position, ...blindspotFinding({ receiver, ...named }, old) };
  return { kind: 'blindspot', path, start, end, edits: [], finding };
}

/** A literal source of a name, rewritten. */
export const sourceOutcome = (source: LiteralSource, newName: string): Outcome => rewrite(source.path, source.start, source.end, newName);

/** A site the rename leaves and does not list. */
export const unrelatedOutcome = (path: string, start: number, end: number): Outcome => ({ kind: 'unrelated', path, start, end, edits: [] });

/** A new error of the edited program at `start`..`end` that no source rewrite resolves. */
export function unresolvedOutcome(path: string, start: number, end: number, old: string): Outcome {
  return { kind: 'blindspot', path, start, end, edits: [], finding: { template: 'refactor.literal-unresolved', position: start, values: { old } } };
}

/** A `--docs` mention: rewritten, else listed. */
export function mentionOutcome(path: string, mention: Mention, rewritten: boolean, old: string, newName: string): Outcome {
  if (rewritten) return rewrite(path, mention.start, mention.end, newName);
  const finding = { template: 'refactor.leftover', position: mention.start, values: { where: mention.where, old } };
  return { kind: 'leftover', path, start: mention.start, end: mention.end, edits: [], finding };
}

/** Each string literal or plain template literal whose whole value is `old` and that no other rule `handled`: a leftover. */
export function literalOutcomes(path: string, source: TS.SourceFile, old: string, handled: (start: number, end: number) => boolean): Outcome[] {
  const out: Outcome[] = [];
  for (const node of walk(source)) {
    if (!(ts().isStringLiteral(node) || ts().isNoSubstitutionTemplateLiteral(node)) || node.text !== old) continue;
    const start = node.getStart(source);
    if (handled(start, node.end)) continue;
    const finding = { template: 'refactor.leftover', position: start, values: { where: 'string', old } };
    out.push({ kind: 'leftover', path, start, end: node.end, edits: [], finding });
  }
  return out;
}

/** A declaration whose name holds `old` as a word sequence: listed. */
export function compoundOutcome(path: string, start: number, end: number, name: string, old: string): Outcome {
  return { kind: 'leftover', path, start, end, edits: [], finding: { template: 'refactor.compound', position: start, values: { name, old } } };
}
