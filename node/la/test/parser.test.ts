// la's manifest through trmv's parser: la's cli.yaml vectors, subcommand help, internal options and bundled scripts.
import { describe, expect, it } from 'vitest';
import { HelpRequested, UsageError, help, manifest, parse } from '../src/contract/index.js';
import { LA_VECTORS, loadYamlFile, plain } from '../../trmv/test/helpers.js';
import { join } from 'node:path';

type Vector = { name: string; command: string; argv: string[]; args?: unknown; exit?: number };

const cases: Vector[] = loadYamlFile(join(LA_VECTORS, 'cli.yaml')).cases ?? [];
const passthrough = (v: Vector): boolean => Boolean(manifest()[v.command]?.passthrough);

describe('cli.yaml', () => {
  it('has vectors', () => {
    expect(cases.length).toBeGreaterThan(0);
  });

  for (const v of cases.filter((c) => !passthrough(c))) {
    it(`${v.command}: ${v.name}`, () => {
      if (v.exit === undefined) {
        expect(plain(parse(v.command, v.argv, manifest()))).toEqual(v.args);
        return;
      }
      let error: unknown;
      try {
        parse(v.command, v.argv, manifest());
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
      parse('la-config', ['get', '--help'], manifest());
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(HelpRequested);
    const text = (error as HelpRequested).text;
    expect(text).toMatch(/^usage: la-config get/);
    expect(text).toContain('positional arguments:');
    expect(text).not.toContain('subcommands:');
  });
});

describe('internal options', () => {
  it.each([
    ['la-doctor', '--contract-hash', ['--twin']],
    ['la-arch-check', '--root', ['--language', '--emit']],
  ])('%s --help omits them', (command, shown, hidden) => {
    const text = help(command, manifest());
    expect(text).toContain(shown);
    for (const option of hidden) expect(text).not.toContain(option);
  });

  it('are still accepted', () => {
    expect(parse('la-doctor', ['--twin'], manifest())).toMatchObject({ twin: true });
    expect(parse('la-arch-check', ['--language', 'typescript', '--emit', 'facts'], manifest())).toMatchObject({
      language: 'typescript',
      emit: 'facts',
    });
  });
});

describe('manifest', () => {
  it('runs la-pr-reviewers through its bundled script', () => {
    expect(manifest()['la-pr-reviewers']?.script).toBe('pr-reviewers.sh');
  });
});
