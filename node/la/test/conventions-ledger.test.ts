// The stealth waiver ledger: loading against the shared schema and matching violations by path, rule and line text.
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ConfigError } from 'type-rename-move/config';
import { describe, expect, it } from 'vitest';
import { loadLedger, waived } from '../src/conventions/ledger.js';

const ENTRY = { path: 'src/a.py', rule: 'import-not-top', line: 'import os', reason: 'optional dependency' };

function ledger(text: string): string {
  const path = join(mkdtempSync(join(tmpdir(), 'la-ledger-')), 'waivers.yaml');
  writeFileSync(path, text);
  return path;
}

function refusal(path: string): unknown {
  try {
    loadLedger(path);
  } catch (error) {
    return error;
  }
  return null;
}

describe('loadLedger', () => {
  it('loads every entry', () => {
    const path = ledger('- {path: src/a.py, rule: import-not-top, line: import os, reason: optional dependency}\n');
    expect(loadLedger(path)).toEqual([ENTRY]);
  });

  it('holds no entries when the ledger is missing', () => {
    expect(loadLedger(join(mkdtempSync(join(tmpdir(), 'la-ledger-')), 'waivers.yaml'))).toEqual([]);
  });

  it.each([
    '- {path: src/a.py, rule: import-not-top, line: import os}\n',
    '- {path: src/a.py, rule: import-not-top, line: import os, reason: x, extra: y}\n',
    '- {path: src/a.py, rule: import-not-top, line: 3, reason: x}\n',
    '{path: src/a.py}\n',
    '- [\n',
  ])('names the file when the ledger is malformed: %j', (text) => {
    const path = ledger(text);
    const error = refusal(path);
    expect(error).toBeInstanceOf(ConfigError);
    expect((error as Error).message).toContain(path);
  });

  it.each(['text-ratio', 'no-such-rule'])('refuses the rule %s, which is not waivable', (rule) => {
    const path = ledger(`- {path: src/a.py, rule: ${rule}, line: import os, reason: x}\n`);
    const error = refusal(path);
    expect(error).toBeInstanceOf(ConfigError);
    expect((error as Error).message).toContain(path);
  });
});

describe('waived', () => {
  it.each(['import os', '        import os', 'import os\r', '\timport os  \r'])(
    'matches the line %j trimmed and without its carriage return',
    (line) => {
      expect(waived([ENTRY], { path: 'src/a.py', rule: 'import-not-top', line })).toBe(true);
    },
  );

  it.each([
    ['src/b.py', 'import-not-top', 'import os'],
    ['src/a.py', 'composite-assert', 'import os'],
    ['src/a.py', 'import-not-top', 'import sys'],
    ['./src/a.py', 'import-not-top', 'import os'],
  ])('needs path, rule and line to match: %s %s %s', (path, rule, line) => {
    expect(waived([ENTRY], { path, rule, line })).toBe(false);
  });

  it('waives every matching violation with one entry', () => {
    const hits = ['import os', '    import os'].map((line) => waived([ENTRY], { path: 'src/a.py', rule: 'import-not-top', line }));
    expect(hits).toEqual([true, true]);
  });
});
