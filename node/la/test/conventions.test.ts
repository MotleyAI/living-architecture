// The neutral conventions pieces: routing by extension, the files label, waivers on carried line text, ratio groups.
import { describe, expect, it } from 'vitest';
import { filesLabel, languageOf, waived } from '../src/conventions/index.js';
import { run, tempRepo } from './cli-run.js';

describe('languageOf', () => {
  it.each([
    ['src/a.py', 'python'],
    ['web/b.ts', 'typescript'],
    ['web/b.tsx', 'typescript'],
    ['x.mts', 'typescript'],
    ['x.cts', 'typescript'],
    ['x.js', 'typescript'],
    ['x.jsx', 'typescript'],
    ['x.mjs', 'typescript'],
    ['x.cjs', 'typescript'],
    ['types/x.d.ts', 'typescript'],
    ['src/données.py', 'python'],
    ['README.md', null],
    ['a.pyc', null],
    ['a.PY', null],
    ['Makefile', null],
  ])('%s -> %s', (path, language) => {
    expect(languageOf(path)).toBe(language);
  });
});

describe('filesLabel', () => {
  it.each([
    [[], 'source'],
    [['python'], '.py'],
    [['typescript'], 'TS/JS'],
    [['python', 'typescript'], '.py and TS/JS'],
    [['typescript', 'python'], '.py and TS/JS'],
  ])('%j -> %s', (languages, label) => {
    expect(filesLabel(languages)).toBe(label);
  });
});

describe('waived', () => {
  it.each([
    ['import a  # ALLOW(import-not-top): cycle', 'import-not-top', 'python', true],
    ['import a  #ALLOW(import-not-top):x', 'import-not-top', 'python', true],
    ["import { a } from 'a'; // ALLOW(import-not-top): generated", 'import-not-top', 'typescript', true],
    ["import { a } from 'a'; # ALLOW(import-not-top): generated", 'import-not-top', 'typescript', false],
    ['import a  // ALLOW(import-not-top): cycle', 'import-not-top', 'python', false],
    ['import a  # ALLOW(composite-assert): wrong rule', 'import-not-top', 'python', false],
    ['import a  # ALLOW(import-not-top):', 'import-not-top', 'python', false],
    ['import a  # allow(import-not-top): lowercase', 'import-not-top', 'python', false],
    ['x = 1  # ALLOW(text-ratio): never', 'text-ratio', 'python', false],
  ])('%s (%s, %s) -> %s', (text, rule, language, expected) => {
    expect(waived({ text, rule, language })).toBe(expected);
  });
});

describe('text-ratio groups', () => {
  const root = tempRepo({
    'src/a.ts': '// one\nexport const a = 1;\n',
    'src/b.ts': 'export const b = 1;\nexport const c = 2;\n',
    'src/a.test.ts': '// one\n// two\n// three\nexport {};\n',
  });
  const files = ['--file', 'src/a.ts', '--file', 'src/b.ts', '--file', 'src/a.test.ts'];

  it('aggregates source and tests separately', () => {
    const { code, out, err } = run(root, 'la-check-conventions', [...files, '--text-ratio-cap', '50']);
    expect(code).toBe(1);
    expect(err).toContain('source text-only ratio 25.0% (1/4, cap 50.0%)');
    expect(err).toContain('tests text-only ratio 75.0% (3/4, cap 50.0%)');
    expect(out).toContain('[text-ratio] tests:');
    expect(out).not.toContain('[text-ratio] source:');
  });

  it('a group at the cap passes', () => {
    expect(run(root, 'la-check-conventions', [...files, '--text-ratio-cap', '75']).code).toBe(0);
  });
});
