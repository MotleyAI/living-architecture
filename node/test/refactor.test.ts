// The TS refactor's shared pieces: the unified diff (shared/vectors/diff.yaml, as rope prints it), the merge of
// per-project edits, whose conflict branch no real TypeScript input reaches, and the writer.
import { chmodSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { message } from '../src/contract/index.js';
import { mergeEdits, RefactorError, unifiedDiff } from '../src/refactor/index.js';
import { writeAll } from '../src/refactor/writer.js';
import { vectors } from './helpers.js';

// A fixed temporary name, so a test can plant a symlink where the writer would write.
vi.mock(import('node:crypto'), async (importOriginal) => {
  const crypto = await importOriginal();
  return { ...crypto, randomBytes: ((size: number) => Buffer.alloc(size)) as typeof crypto.randomBytes };
});
const TEMP_SUFFIX = `.${'00'.repeat(8)}.la-tmp`;

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
    const edits = [edit(0, 'bar'), edit(0, 'baz')];
    expect(() => mergeEdits(edits)).toThrow(new RefactorError('projects disagree on an edit in src/a.ts'));
  });

  it('refuses overlapping spans', () => {
    const edits = [edit(0, 'bar', 5), edit(2, 'baz')];
    expect(() => mergeEdits(edits)).toThrow(RefactorError);
  });
});

describe('writeAll', () => {
  it('keeps a replaced file’s mode', () => {
    const path = join(mkdtempSync(join(tmpdir(), 'writer-')), 'run.ts');
    writeFileSync(path, 'a\n');
    chmodSync(path, 0o755);
    writeAll([{ path, old: 'a\n', text: 'b\n' }], [], (p) => p);
    expect(statSync(path).mode & 0o7777).toBe(0o755);
  });

  it('leaves no temporary file beside a written one', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const path = join(dir, 'a.ts');
    writeFileSync(path, 'a\n');
    writeAll([{ path, old: 'a\n', text: 'b\n' }], [], (p) => p);
    expect([readFileSync(path, 'utf8'), readdirSync(dir)]).toEqual(['b\n', ['a.ts']]);
  });

  it('refuses to write through a symlink planted at its temporary name', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const [path, outside] = [join(dir, 'a.ts'), join(dir, 'outside.txt')];
    writeFileSync(path, 'a\n');
    writeFileSync(outside, 'keep\n');
    const planted = join(dir, `.a.ts${TEMP_SUFFIX}`);
    symlinkSync(outside, planted);
    expect(() => writeAll([{ path, old: 'a\n', text: 'b\n' }], [], (p) => p)).toThrow(message('refactor.write-failed', { path }));
    expect([readFileSync(path, 'utf8'), readFileSync(outside, 'utf8'), lstatSync(planted).isSymbolicLink()]).toEqual(['a\n', 'keep\n', true]);
  });

  it.skipIf(process.getuid?.() === 0)('names the source of a failed move, as the Python twin does, and restores the writes', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const [written, from, locked] = [join(dir, 'a.ts'), join(dir, 'b.ts'), join(dir, 'locked')];
    writeFileSync(written, 'a\n');
    chmodSync(written, 0o755);
    writeFileSync(from, 'b\n');
    mkdirSync(locked);
    chmodSync(locked, 0o555);
    try {
      const run = (): void => writeAll([{ path: written, old: 'a\n', text: 'A\n' }], [[from, join(locked, 'b.ts')]], (p) => p);
      expect(run).toThrow(message('refactor.write-failed', { path: from }));
    } finally {
      chmodSync(locked, 0o755);
    }
    expect([readFileSync(written, 'utf8'), statSync(written).mode & 0o7777, readFileSync(from, 'utf8')]).toEqual(['a\n', 0o755, 'b\n']);
  });
});
