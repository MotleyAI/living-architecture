// Manifest parser vectors, through src/cli/parser.ts: parse(command, argv) returns the parsed mapping keyed by dest
// (defaults and `subcommand` included; a passthrough command gives {argv}) or throws UsageError (exitCode 2);
// help(command) returns the command's --help text.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { HelpRequested, UsageError, help, parse } from '../src/cli/parser.js';
import { manifest } from '../src/contract/index.js';
import { SNAPSHOT, plain, vectors } from './helpers.js';

type Vector = { name: string; command: string; argv: string[]; args?: unknown; exit?: number };

const cases: Vector[] = vectors('cli.yaml')?.cases ?? [];

describe('cli.yaml', () => {
  it('has vectors', () => {
    expect(cases.length).toBeGreaterThan(0);
  });

  for (const v of cases) {
    it(`${v.command}: ${v.name}`, () => {
      if (v.exit === undefined) {
        expect(plain(parse(v.command, v.argv))).toEqual(v.args);
        return;
      }
      let error: unknown;
      try {
        parse(v.command, v.argv);
      } catch (e) {
        error = e;
      }
      expect(error).toBeInstanceOf(UsageError);
      expect((error as UsageError).exitCode).toBe(v.exit);
    });
  }
});

describe('subcommand help', () => {
  it('describes the subcommand, not its parent', () => {
    let error: unknown;
    try {
      parse('la-config', ['get', '--help']);
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(HelpRequested);
    const text = (error as HelpRequested).text;
    expect(text).toMatch(/^usage: la-config get/);
    expect(text).toContain('positional arguments:');
    expect(text).toContain('key');
    expect(text).not.toContain('subcommands:');
  });
});

describe('internal options', () => {
  it.each([
    ['la-doctor', '--contract-hash', ['--twin']],
    ['la-arch-check', '--root', ['--language', '--emit']],
  ])('%s --help omits them', (command, shown, hidden) => {
    const text = help(command);
    expect(text).toContain(shown);
    for (const option of hidden) expect(text).not.toContain(option);
  });

  it('are still accepted', () => {
    expect(parse('la-doctor', ['--twin'])).toMatchObject({ twin: true });
    expect(parse('la-arch-check', ['--language', 'typescript', '--emit', 'facts'])).toMatchObject({
      language: 'typescript',
      emit: 'facts',
    });
  });
});

describe('manifest', () => {
  it('has no per-command gate', () => {
    expect(Object.entries(manifest()).filter(([, spec]) => 'gate' in (spec as object)).map(([name]) => name)).toEqual([]);
    const header = readFileSync(join(SNAPSHOT, 'cli.yaml'), 'utf8').split('\ncommands:')[0];
    expect(header).not.toContain('gate');
  });

  it('runs la-pr-reviewers through its bundled script', () => {
    expect(manifest()['la-pr-reviewers']?.script).toBe('pr-reviewers.sh');
  });
});
