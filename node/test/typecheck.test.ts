// la-typecheck's neutral pieces (command splitting, exit combination, applicability) and the tsc diagnostic grammar.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseTscOutput } from '../src/lang/index.js';
import { combinedExit, splitCommand } from '../src/typecheck/index.js';
import { run, tempRepo } from './cli-run.js';
import { vectors } from './helpers.js';

type Split = { name: string; text: string; words?: string[]; error?: boolean };

describe('command-split.yaml', () => {
  const cases: Split[] = vectors('command-split.yaml')?.cases ?? [];
  it('has vectors', () => {
    expect(cases.length).toBeGreaterThan(0);
  });
  for (const v of cases) {
    it(v.name, () => {
      if (v.error) expect(() => splitCommand(v.text)).toThrow();
      else expect(splitCommand(v.text)).toEqual(v.words);
    });
  }
});

describe('combinedExit', () => {
  it.each([
    [[], 0],
    [[0], 0],
    [[0, 1], 1],
    [[1, 0], 1],
    [[2, 1], 2],
    [[0, 2], 2],
  ])('%j -> %i', (codes, expected) => {
    expect(combinedExit(codes)).toBe(expected);
  });
});

describe('parseTscOutput', () => {
  it('reads file, position, code and message', () => {
    const out = "src/a.ts(3,7): error TS2322: Type 'string' is not assignable to type 'number'.\n";
    expect(parseTscOutput(out)).toEqual({
      diagnostics: [
        { file: 'src/a.ts', line: 3, col: 7, code: 'TS2322', message: "Type 'string' is not assignable to type 'number'." },
      ],
      globals: [],
    });
  });

  it('keeps indented continuation lines in the message', () => {
    const out = [
      "src/a.ts(2,7): error TS2322: Type '{ a: { b: string; }; }' is not assignable to type 'T'.",
      "  The types of 'a.b' are incompatible between these types.",
      "    Type 'string' is not assignable to type 'number'.",
      "src/a.ts(5,1): error TS2304: Cannot find name 'z'.",
      '',
    ].join('\n');
    expect(parseTscOutput(out).diagnostics.map((d) => [d.line, d.message])).toEqual([
      [
        2,
        "Type '{ a: { b: string; }; }' is not assignable to type 'T'.\n" +
          "  The types of 'a.b' are incompatible between these types.\n" +
          "    Type 'string' is not assignable to type 'number'.",
      ],
      [5, "Cannot find name 'z'."],
    ]);
  });

  it('takes the longest path, spaces and parentheses included', () => {
    const out = "src/my file (copy).ts(2,7): error TS2304: Cannot find name 'x'.\nsrc/odd (1,2).ts(3,4): error TS2304: Cannot find name 'y'.\n";
    expect(parseTscOutput(out).diagnostics.map((d) => [d.file, d.line, d.col])).toEqual([
      ['src/my file (copy).ts', 2, 7],
      ['src/odd (1,2).ts', 3, 4],
    ]);
  });

  it('reports a diagnostic without a file as global', () => {
    const line = "error TS18003: No inputs were found in config file 'tsconfig.json'.";
    expect(parseTscOutput(`${line}\n`)).toEqual({ diagnostics: [], globals: [line] });
  });

  it('ignores lines that are neither diagnostics nor continuations', () => {
    const out = "Version 6.0.3\nsrc/a.ts(1,1): error TS2304: Cannot find name 'q'.\n";
    expect(parseTscOutput(out).diagnostics).toEqual([
      { file: 'src/a.ts', line: 1, col: 1, code: 'TS2304', message: "Cannot find name 'q'." },
    ]);
  });
});

describe('applicable languages', () => {
  const FAKE_TSC = '#!/bin/sh\necho "$*" >> tsc.log\nexit 0\n';
  const tscCalls = (root: string) =>
    existsSync(join(root, 'tsc.log')) ? readFileSync(join(root, 'tsc.log'), 'utf8').split('\n').filter(Boolean) : [];

  it('a tsconfig.json and a TS file make TypeScript apply; a missing baseline counts as empty', () => {
    const root = tempRepo({ 'tsconfig.json': '{}', 'src/a.ts': 'export {};\n', 'node_modules/.bin/tsc': FAKE_TSC });
    expect(run(root, 'la-typecheck', []).code).toBe(0);
    expect(tscCalls(root)).toEqual(['--noEmit --pretty false']);
  });

  it('TS files without a tsconfig.json check nothing', () => {
    const root = tempRepo({ 'src/a.ts': 'export {};\n', 'node_modules/.bin/tsc': FAKE_TSC });
    const { code, err } = run(root, 'la-typecheck', []);
    expect(code).toBe(0);
    expect(err).toContain('la-typecheck: nothing to check');
    expect(tscCalls(root)).toEqual([]);
  });

  it('null turns TypeScript off', () => {
    const root = tempRepo({
      'tsconfig.json': '{}',
      'src/a.ts': 'export {};\n',
      'living-architecture.yaml': 'commands: {typecheck: {typescript: null}}\n',
      'node_modules/.bin/tsc': FAKE_TSC,
    });
    expect(run(root, 'la-typecheck', []).code).toBe(0);
    expect(tscCalls(root)).toEqual([]);
  });

  it('an explicit command applies without a marker or files', () => {
    const root = tempRepo({
      'living-architecture.yaml': "commands: {typecheck: {typescript: 'tsc -p web'}}\n",
      'node_modules/.bin/tsc': FAKE_TSC,
    });
    expect(run(root, 'la-typecheck', []).code).toBe(0);
    expect(tscCalls(root)).toEqual(['-p web --pretty false']);
  });

  it('exempt files do not count', () => {
    const root = tempRepo({
      'tsconfig.json': '{}',
      'gen/a.ts': 'export {};\n',
      'living-architecture.yaml': "conventions: {exempt: ['gen/*']}\n",
      'node_modules/.bin/tsc': FAKE_TSC,
    });
    expect(run(root, 'la-typecheck', []).code).toBe(0);
    expect(tscCalls(root)).toEqual([]);
  });
});
