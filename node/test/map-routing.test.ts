// dr-refactor rename-map is routed by its entries' files: another language's map goes to its twin with the raw argv.
import { chmodSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { message } from '../src/contract/index.js';
import * as twin from '../src/twin/index.js';
import { mapYaml, refactor, tsProject } from './refactor-project.js';

vi.mock('../src/twin/index.js', async (original) => ({ ...(await original<typeof twin>()), forward: vi.fn(() => 7) }));

describe('rename-map routing', () => {
  it('hands a Python map to the Python twin with the raw argv', () => {
    const root = tsProject({ 'pkg/a.py': 'def f() -> None:\n    pass\n', 'map.yaml': mapYaml([{ file: 'pkg/a.py', symbol: 'f', new_name: 'g' }]) });
    const argv = ['--apply', 'rename-map', 'map.yaml', '--docs'];
    expect(refactor(root, ...argv)).toEqual({ code: 7, out: '', err: '' });
    expect(vi.mocked(twin.forward)).toHaveBeenCalledWith('dr-refactor', 'python', argv, realpathSync(root));
  });

  it('refuses an entry file of no supported language', () => {
    const root = tsProject({ 'map.yaml': mapYaml([{ file: 'notes.txt', symbol: 'f', new_name: 'g' }]) });
    expect(refactor(root, 'rename-map', 'map.yaml')).toEqual({ code: 1, out: '', err: `${message('refactor.unsupported-extension', { path: 'notes.txt' })}\n` });
  });

  it.each(['missing.yaml', 'empty.yaml', 'scalar.yaml'])('a map that holds no entries is invalid (%s)', (map) => {
    const root = tsProject({ 'empty.yaml': '[]\n', 'scalar.yaml': 'file: a.ts\n' });
    expect(refactor(root, 'rename-map', map)).toEqual({ code: 2, out: '', err: `${message('refactor.map-invalid', { map, index: 1 })}\n` });
  });

  it.skipIf(process.platform === 'win32' || process.getuid?.() === 0)('a map that cannot be read is invalid', () => {
    const root = tsProject({ 'a.ts': 'export const f = 1;\n', 'map.yaml': mapYaml([{ file: 'a.ts', symbol: 'f', new_name: 'g' }]) });
    chmodSync(join(root, 'map.yaml'), 0);
    try {
      expect(refactor(root, 'rename-map', 'map.yaml')).toEqual({ code: 2, out: '', err: `${message('refactor.map-invalid', { map: 'map.yaml', index: 1 })}\n` });
    } finally {
      chmodSync(join(root, 'map.yaml'), 0o644);
    }
  });
});
