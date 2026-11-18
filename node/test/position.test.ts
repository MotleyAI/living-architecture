// A refactor's position map: edits, moved files and moved declarations.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { mapPosition, movedOffsets, type PositionMap } from '../src/refactor/position.js';
import { entryRefusal, read, refactor, tsProject } from './refactor-project.js';

describe('movedOffsets', () => {
  it('maps an unchanged text by its place in the inserted text', () => {
    const offset = movedOffsets('const a = 1;', '\nconst a = 1;\n');
    expect([offset(0), offset(6)]).toEqual([1, 7]);
  });

  it('maps a reindented text character by character', () => {
    const moved = 'function f() {\n  return 1;\n}';
    const inserted = 'export function f() {\n    return 1;\n}\n';
    const offset = movedOffsets(moved, inserted);
    expect(offset(moved.indexOf('return'))).toBe(inserted.indexOf('return'));
    expect(offset(moved.indexOf('1'))).toBe(inserted.indexOf('1'));
  });

  it('maps nothing when the move rewrote more than white space', () => {
    expect(movedOffsets('const a = 1;', 'const b = 1;')(0)).toBeNull();
  });
});

describe('mapPosition', () => {
  const map: PositionMap = {
    edits: new Map([
      ['a.ts', [{ path: 'a.ts', start: 0, length: 10, newText: '' }]],
      ['b.ts', [{ path: 'b.ts', start: 2, length: 3, newText: 'x' }, { path: 'b.ts', start: 20, length: 0, newText: '0123456789' }]],
    ]),
    moves: new Map([['c.ts', 'd/c.ts']]),
    spans: [{ from: 'a.ts', start: 0, end: 10, to: 'b.ts', at: 20, offset: (inside) => inside }],
  };

  it('follows an edit, a moved file and a moved declaration', () => {
    expect(mapPosition(map, 'b.ts', 10)).toEqual({ file: 'b.ts', position: 8 });
    expect(mapPosition(map, 'c.ts', 4)).toEqual({ file: 'd/c.ts', position: 4 });
    expect(mapPosition(map, 'a.ts', 4)).toEqual({ file: 'b.ts', position: 22 });
    expect(mapPosition(map, 'a.ts', 12)).toEqual({ file: 'a.ts', position: 2 });
  });
});

describe('name conflicts', () => {
  const f = 'export function f(x: number): number {\n  const y = 2;\n  return x + y;\n}\n';

  it('refuses a rename to a name its scope already declares', () => {
    const root = tsProject({ 'src/f.ts': f });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/f.ts', '--symbol', 'f(x)', '--new-name', 'y');
    const conflict = message('refactor.name-conflict', { name: 'y', path: 'src/f.ts', line: 2 });
    expect(result).toEqual({ code: 1, out: '', err: `${entryRefusal('src/f.ts f(x)', conflict)}\n` });
    expect(read(root, 'src/f.ts')).toBe(f);
  });

  it('takes a name another scope or a library declares', () => {
    const root = tsProject({ 'src/f.ts': `${f}\nexport function g(y: number): number {\n  return y;\n}\n` });
    expect(refactor(root, 'rename', '--file', 'src/f.ts', '--symbol', 'g(y)', '--new-name', 'x').code).toBe(0);
    expect(refactor(root, 'rename', '--file', 'src/f.ts', '--symbol', 'g', '--new-name', 'parseInt').code).toBe(0);
  });
});
