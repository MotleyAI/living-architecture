// `dr-refactor`'s phases and progress lines on stderr, and the refusals a run collects into one report.
import { message } from '../contract/index.js';

/** A finding's lines and its exit code. */
export interface Refusal {
  lines: string[];
  code: number;
}

export const refusal = (text: string, code = 1): Refusal => ({ lines: [text], code });

/** The run refuses with `refusals`, printed in order; the exit code is the highest of theirs. */
export class Refused extends Error {
  constructor(readonly refusals: Refusal[]) {
    super(refusals.flatMap((r) => r.lines).join('\n'));
  }

  get lines(): string[] {
    return this.refusals.flatMap((r) => r.lines);
  }

  get code(): number {
    return Math.max(1, ...this.refusals.map((r) => r.code));
  }
}

/** `refusals` in order, each distinct one once. */
export function unique(refusals: Refusal[]): Refusal[] {
  const seen = new Set<string>();
  return refusals.filter((r) => {
    const key = JSON.stringify(r);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** The map indexes an entry or group stands for. */
function labels(indexes: number[]): string {
  if (indexes.length === 1) return message('refactor.progress-entry', { index: indexes[0] });
  return message('refactor.progress-entries', { indexes: indexes.join(', ') });
}

const print = (text: string): void => {
  process.stderr.write(`${text}\n`);
};

/** Writes the phase and progress lines as they happen. */
export class Progress {
  phase(name: string): void {
    print(message('refactor.progress-phase', { phase: name }));
  }

  /** `[references n/count]`: an entry's reference search starts. */
  item(n: number, count: number, indexes: number[], old: string, newName: string): void {
    print(message('refactor.progress-item', { phase: 'references', n, count, entries: labels(indexes), old, new: newName }));
  }

  /** `[rules n/count]`: a group is done, clean or refused with its refusal lines. */
  result(n: number, count: number, indexes: number[], old: string, newNames: string, refused: string[]): void {
    const fields = { phase: 'rules', n, count, entries: labels(indexes), old, new: newNames };
    if (refused.length === 0) {
      print(message('refactor.progress-clean', fields));
      return;
    }
    print(message('refactor.progress-refused', { ...fields, refusals: refused.length }));
    for (const line of refused) print(line);
  }
}
