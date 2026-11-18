// The module rename taken check on a case-insensitive filesystem, simulated under one temporary directory.
import * as fs from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { takenBy } from '../src/refactor/module-rename.js';

const state = vi.hoisted(() => ({ root: '' }));

vi.mock('node:fs', async (importOriginal) => {
  const real = await importOriginal<typeof import('node:fs')>();
  /** `path` under the root with its last part spelled as the entry it case-insensitively names. */
  const fold = (path: fs.PathLike): string => {
    const text = path.toString();
    if (state.root === '' || !text.startsWith(state.root)) return text;
    const cut = text.lastIndexOf('/');
    const dir = text.slice(0, cut);
    const wanted = text.slice(cut + 1).toLowerCase();
    const hit = real.existsSync(dir) ? real.readdirSync(dir).find((entry) => entry.toLowerCase() === wanted) : undefined;
    return hit === undefined ? text : `${dir}/${hit}`;
  };
  return { ...real, existsSync: (path: fs.PathLike) => real.existsSync(fold(path)), statSync: (path: fs.PathLike) => real.statSync(fold(path)) };
});

const project = (...names: string[]): string => {
  state.root = fs.realpathSync(fs.mkdtempSync(join(tmpdir(), 'la-taken-')));
  for (const name of names) fs.writeFileSync(join(state.root, name), 'export {};\n');
  return state.root;
};

afterEach(() => {
  if (state.root !== '') fs.rmSync(state.root, { recursive: true, force: true });
  state.root = '';
});

describe('module rename taken check, case-insensitive', () => {
  it('a case-only rename is not taken by the module itself', () => {
    const root = project('a.ts');
    expect(takenBy(join(root, 'a.ts'), 'A')).toBeNull();
  });

  it('another file spelling the new name in another case takes it', () => {
    const root = project('a.ts', 'b.ts');
    expect(takenBy(join(root, 'a.ts'), 'B')).toBe(join(root, 'B.ts'));
  });

  it('a hard link to the module under the new name takes it', () => {
    const root = project('a.ts');
    fs.linkSync(join(root, 'a.ts'), join(root, 'b.ts'));
    expect(takenBy(join(root, 'a.ts'), 'b')).toBe(join(root, 'b.ts'));
  });
});
