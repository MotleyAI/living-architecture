// The TS refactor's shared pieces: the unified diff (shared/vectors/diff.yaml, as rope prints it) and the merge of
// per-project edits, whose conflict branch no real TypeScript input reaches.
import { describe, expect, it } from 'vitest';
import { mergeEdits, RefactorError, unifiedDiff } from '../src/refactor/index.js';
import { vectors } from './helpers.js';

type DiffVector = { name: string; path: string; old: string; new: string; diff: string };

describe('diff.yaml', () => {
  const cases: DiffVector[] = vectors('diff.yaml')?.cases ?? [];
  it('has vectors', () => {
    expect(cases.length).toBeGreaterThan(0);
  });
  for (const v of cases) {
    it(v.name, () => {
      expect(unifiedDiff(v.old, v.new, v.path)).toBe(v.diff);
    });
  }
});

describe('mergeEdits', () => {
  const edit = (start: number, newText: string, length = 3) => ({ path: 'src/a.ts', start, length, newText });

  it('keeps one copy of identical edits from two projects', () => {
    expect(mergeEdits([edit(0, 'bar'), edit(10, 'bar'), edit(0, 'bar')])).toEqual(
      new Map([['src/a.ts', [edit(0, 'bar'), edit(10, 'bar')]]]),
    );
  });

  it('refuses differing edits to one span', () => {
    expect(() => mergeEdits([edit(0, 'bar'), edit(0, 'baz')])).toThrow(
      new RefactorError('projects disagree on an edit in src/a.ts'),
    );
  });

  it('refuses overlapping spans', () => {
    expect(() => mergeEdits([edit(0, 'bar', 5), edit(2, 'baz')])).toThrow(RefactorError);
  });
});
