// The TS refactor's shared pieces: the unified diff (shared/vectors/diff.yaml, as rope prints it), the merge of
// per-project edits, whose conflict branch no real TypeScript input reaches, and the writer.
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, statSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { message } from '../src/contract/index.js';
import { mergeEdits, RefactorError, unifiedDiff } from '../src/refactor/index.js';
import { Refactor } from '../src/refactor/session.js';
import { writeAll } from '../src/refactor/writer.js';
import { vectors } from './helpers.js';
import { commitAll, gitStatus, read, tsProject } from './refactor-project.js';

// A fixed temporary name, so a test can plant a symlink where the writer would write.
vi.mock(import('node:crypto'), async (importOriginal) => {
  const crypto = await importOriginal();
  return { ...crypto, randomBytes: ((size: number) => Buffer.alloc(size)) as typeof crypto.randomBytes };
});
const TEMP_SUFFIX = `.${'00'.repeat(8)}.la-tmp`;

// Fault injection for the writer: `open` sees every opened path, `spawn` may answer a spawned command's status.
const hooks = vi.hoisted(() => {
  const state: { open: (path: string) => void; spawn: (args: readonly string[]) => number | null } = { open: () => undefined, spawn: () => null };
  return state;
});
vi.mock(import('node:fs'), async (importOriginal) => {
  const fs = await importOriginal();
  const openSync = ((path: Parameters<typeof fs.openSync>[0], ...rest: unknown[]) => {
    hooks.open(String(path));
    return (fs.openSync as (...args: unknown[]) => number)(path, ...rest);
  }) as typeof fs.openSync;
  return { ...fs, openSync };
});
vi.mock(import('node:child_process'), async (importOriginal) => {
  const cp = await importOriginal();
  const spawnSync = ((command: string, args: readonly string[] = [], options?: object) => {
    const status = hooks.spawn(args);
    if (status === null) return cp.spawnSync(command, args, options);
    return { pid: 0, output: [], stdout: Buffer.alloc(0), stderr: Buffer.alloc(0), status, signal: null };
  }) as typeof cp.spawnSync;
  return { ...cp, spawnSync };
});
afterEach(() => {
  hooks.open = () => undefined;
  hooks.spawn = () => null;
});

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
    writeAll(dirname(path), [{ path, old: 'a\n', text: 'b\n' }], [], (p) => p);
    expect(statSync(path).mode & 0o7777).toBe(0o755);
  });

  it('leaves no temporary file beside a written one', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const path = join(dir, 'a.ts');
    writeFileSync(path, 'a\n');
    writeAll(dirname(path), [{ path, old: 'a\n', text: 'b\n' }], [], (p) => p);
    expect([readFileSync(path, 'utf8'), readdirSync(dir)]).toEqual(['b\n', ['a.ts']]);
  });

  it('refuses to write through a symlink planted at its temporary name', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const [path, outside] = [join(dir, 'a.ts'), join(dir, 'outside.txt')];
    writeFileSync(path, 'a\n');
    writeFileSync(outside, 'keep\n');
    const planted = join(dir, `.a.ts${TEMP_SUFFIX}`);
    symlinkSync(outside, planted);
    expect(() => writeAll(dir, [{ path, old: 'a\n', text: 'b\n' }], [], (p) => p)).toThrow(message('refactor.write-failed', { path }));
    expect([readFileSync(path, 'utf8'), readFileSync(outside, 'utf8'), lstatSync(planted).isSymbolicLink()]).toEqual(['a\n', 'keep\n', true]);
  });

  it('moves a tracked file with git, so the move is staged, and an untracked one without', () => {
    const root = tsProject({ 'src/tracked.ts': 'export {};\n', 'src/sub/keep.ts': 'export {};\n' });
    commitAll(root);
    writeFileSync(join(root, 'src/loose.ts'), 'export {};\n');
    const moves: [string, string][] = [
      [join(root, 'src/tracked.ts'), join(root, 'src/sub/tracked.ts')],
      [join(root, 'src/loose.ts'), join(root, 'src/sub/loose.ts')],
    ];
    writeAll(root, [], moves, (p) => p);
    expect(gitStatus(root)).toEqual(expect.arrayContaining(['R  src/tracked.ts -> src/sub/tracked.ts', '?? src/sub/loose.ts']));
  });

  it('attempts every restoration and names the paths left changed', () => {
    const dir = mkdtempSync(join(tmpdir(), 'writer-'));
    const [a, b, c] = ['a.ts', 'b.ts', 'c.ts'].map((name) => join(dir, name)) as [string, string, string];
    for (const path of [a, b, c]) writeFileSync(path, 'x\n');
    const opened = new Map<string, number>();
    hooks.open = (path) => {
      const name = /\.([^/]+)\.[0-9a-f]+\.la-tmp$/.exec(path)?.[1] ?? '';
      opened.set(name, (opened.get(name) ?? 0) + 1);
      if ((name === 'c.ts' && opened.get(name) === 1) || (name === 'b.ts' && opened.get(name) === 2)) throw new Error(name);
    };
    const writes = [a, b, c].map((path) => ({ path, old: 'x\n', text: 'y\n' }));
    expect(() => writeAll(dir, writes, [], (p) => p)).toThrow(message('refactor.rollback-failed', { path: c, paths: b }));
    expect(readFileSync(a, 'utf8')).toBe('x\n');
  });

  it('rolls back a move that fails after moving', () => {
    const root = tsProject({ 'src/a.ts': 'export {};\n', 'src/sub/keep.ts': 'export {};\n' });
    commitAll(root);
    hooks.spawn = (args) => {
      if (args[0] !== 'mv' || args[2] !== 'src/a.ts') return null;
      renameSync(join(root, args[2]), join(root, args[3] ?? ''));
      return 1;
    };
    const [from, to] = [join(root, 'src/a.ts'), join(root, 'src/sub/a.ts')];
    expect(() => writeAll(root, [], [[from, to]], (p) => p)).toThrow(message('refactor.write-failed', { path: from }));
    expect([existsSync(from), existsSync(to)]).toEqual([true, false]);
  });

  it('stages a tracked move below the git root', () => {
    const root = tsProject({ 'proj/a.ts': 'export {};\n', 'proj/sub/keep.ts': 'export {};\n' });
    commitAll(root);
    writeAll(join(root, 'proj'), [], [[join(root, 'proj/a.ts'), join(root, 'proj/sub/a.ts')]], (p) => p);
    expect(gitStatus(root)).toContain('R  proj/a.ts -> proj/sub/a.ts');
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
      const run = (): void => writeAll(dir, [{ path: written, old: 'a\n', text: 'A\n' }], [[from, join(locked, 'b.ts')]], (p) => p);
      expect(run).toThrow(message('refactor.write-failed', { path: from }));
    } finally {
      chmodSync(locked, 0o755);
    }
    expect([readFileSync(written, 'utf8'), statSync(written).mode & 0o7777, readFileSync(from, 'utf8')]).toEqual(['a\n', 0o755, 'b\n']);
  });
});

describe('Refactor.emit', () => {
  it('refuses a file changed after the program read it', () => {
    const root = tsProject({ 'src/a.ts': 'export const a = 1;\n' });
    const file = join(root, 'src/a.ts');
    const r = new Refactor({ project: root, apply: true, subcommand: 'rename' });
    r.services(file)[0]?.getProgram();
    writeFileSync(file, '// edited\nexport const a = 1;\n');
    const edits = new Map([[file, [{ path: file, start: 13, length: 1, newText: 'b' }]]]);
    expect(() => r.emit([], edits, [])).toThrow(message('refactor.file-changed', { path: 'src/a.ts' }));
    expect(read(root, 'src/a.ts')).toBe('// edited\nexport const a = 1;\n');
  });
});
