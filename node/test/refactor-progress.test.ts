// dr-refactor phases: the map loader's every invalid entry and the keep text check.
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { MapError, loadMap } from '../src/refactor/map.js';
import { spelledLines } from '../src/refactor/sites.js';
import { refactorRaw, tsProject } from './refactor-project.js';

const CHECKS = '[resolve]\n[checks]\n';
const FOO = 'export function foo(): number {\n  return 1;\n}\n';

describe('the map loader', () => {
  it('names every invalid entry', () => {
    const root = tsProject({});
    const path = join(root, 'map.yaml');
    writeFileSync(
      path,
      '- {file: a.ts, symbol: f, new_name: g}\n- {file: a.ts, symbol: f}\n- {file: a.ts, symbol: h, new_name: i}\n- {file: a.ts, new_name: j}\n',
    );
    const expected = [2, 4].map((index) => message('refactor.map-invalid', { map: 'map.yaml', index })).join('\n');
    expect(() => loadMap(path, 'map.yaml')).toThrow(new MapError(expected));
  });
});

describe('the keep text check', () => {
  it.each([
    ['as written', 'const a = 1;\nconst b = load();\n', [2]],
    ['absent', 'const x = 1;\n', []],
    ['string escape', 'const n = "lo\\x61d";\n', [1]],
    ['identifier escape', 'store.lo\\u0061d();\n', [1]],
    ['comment', '// load the store\n', [1]],
    ['no NFKC', 'const ｌoad = 1;\n', []],
  ])('%s', (_kind, text, lines) => {
    expect([...spelledLines(text, new Set(['load']))].sort()).toEqual(lines);
  });

  it('is skipped when an unresolved entry spells no name', () => {
    const root = tsProject({
      'src/a.ts': FOO,
      'README.md': '# Nothing here\n',
      'map.yaml': '- {file: src/a.ts, symbol: foo, new_name: bar}\n- {file: src/a.ts, line: 99, new_name: baz}\n',
    });
    expect(refactorRaw(root, 'rename-map', 'map.yaml', '--keep', 'README.md')).toEqual({
      code: 1,
      out: '',
      err: `${CHECKS}${message('refactor.line-out-of-range', { line: 99, count: 3 })}\n`,
    });
  });
});
