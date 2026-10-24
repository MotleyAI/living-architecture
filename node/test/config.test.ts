// The git-ignored local override: file names from config.yaml, the local schema's cross-file `$ref`s, the raw
// loader's merge and order of checks, and the `la-config` notes.
import * as fs from 'node:fs';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { ConfigError, currentFormat, explicitTypecheck, loadConfig, loadRaw, resolveConfig } from '../src/config/index.js';
import { configFile, localConfigFile, schema, validate } from '../src/contract/index.js';
import { run } from './cli-run.js';
import { plain } from './helpers.js';

vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof fs>();
  return { ...actual, readFileSync: vi.fn(actual.readFileSync) };
});

const COMMITTED = 'living-architecture.yaml';
const LOCAL = 'living-architecture.local.yaml';

function repo(files: { committed?: string; local?: string }): string {
  const root = mkdtempSync(join(tmpdir(), 'la-local-'));
  if (files.committed !== undefined) writeFileSync(join(root, COMMITTED), files.committed);
  if (files.local !== undefined) writeFileSync(join(root, LOCAL), files.local);
  return root;
}

function configError(root: string): string {
  try {
    loadConfig(root);
  } catch (error) {
    if (error instanceof ConfigError) return error.message;
    throw error;
  }
  throw new Error('expected a ConfigError');
}

describe('config file names', () => {
  it('come from config.yaml', () => {
    expect([configFile(), localConfigFile()]).toEqual([COMMITTED, LOCAL]);
  });
});

describe('local schema', () => {
  it('resolves its cross-file $refs', () => {
    const local = schema('living-architecture.local');
    expect(validate(local, { tracker: 'github', reviewers: { codex: false } })).toEqual([]);
    const enumErrors = validate(local, { tracker: 'jira' });
    expect(enumErrors).toHaveLength(1);
    expect(enumErrors[0]).toMatch(/^tracker: /);
    const typeErrors = validate(local, { reviewers: { codex: 'yes' } });
    expect(typeErrors).toHaveLength(1);
    expect(typeErrors[0]).toMatch(/^reviewers\.codex: /);
  });

  it('keeps each schema apart after a cross-file $ref', () => {
    expect(validate(schema('living-architecture.local'), { tracker: 'none' })).toEqual([]);
    expect(validate(schema('living-architecture'), { openspec: false })).toEqual([]);
    expect(validate(schema('living-architecture.local'), { openspec: false })).not.toEqual([]);
  });

  it.each([
    { tracker: 'linear' },
    { tracker: 'none' },
    { tracker: 'jira' },
    { tracker: null },
    { reviewers: { codex: false } },
    { reviewers: { codex: 'yes' } },
    { reviewers: {} },
    { reviewers: null },
  ])('follows the main schema for %j', (document) => {
    const validMain = validate(schema('living-architecture'), document).length === 0;
    expect(validate(schema('living-architecture.local'), document).length === 0).toBe(validMain);
  });

  it.each([
    [{ openspec: false }, 'openspec'],
    [{ commands: { test: 'pytest' } }, 'commands'],
    [{ reviewers: { sonar: { project_key: 'o_r' } } }, 'sonar'],
  ])('refuses the repo decision %j', (document, key) => {
    const errors = validate(schema('living-architecture.local'), document);
    expect(errors).not.toEqual([]);
    expect(errors.join('; ')).toContain(key);
  });
});

describe('loading with a local file', () => {
  it('overrides committed values', () => {
    const config = loadConfig(repo({ committed: 'tracker: github\nreviewers: {codex: true}\n', local: 'tracker: none\nreviewers: {codex: false}\n' }));
    expect([config.tracker, config.reviewers.codex]).toEqual(['none', false]);
  });

  it('keeps sibling keys', () => {
    const config = loadConfig(repo({ committed: 'openspec: false\nreviewers: {sonar: {project_key: o_r}}\n', local: 'reviewers: {codex: false}\n' }));
    expect(config.reviewers).toEqual({ codex: false, sonar: { project_key: 'o_r' } });
    expect(config.openspec).toBe(false);
  });

  it('merges over the defaults without a committed file', () => {
    expect(loadConfig(repo({ local: 'tracker: none\n' }))).toEqual(resolveConfig(new Map([['tracker', 'none']])));
  });

  it.each(['', '# my overrides\n', 'reviewers: {}\n'])('overrides nothing with %j', (text) => {
    const root = repo({ committed: 'tracker: github\n', local: text });
    expect(loadConfig(root)).toEqual(resolveConfig(new Map([['tracker', 'github']])));
    expect(loadRaw(root).overrides).toEqual([]);
  });

  it('lists overrides in schema order, even when equal', () => {
    expect(loadRaw(repo({ committed: 'tracker: github\n', local: 'reviewers: {codex: false}\ntracker: github\n' })).overrides).toEqual([
      'tracker',
      'reviewers.codex',
    ]);
  });

  it('returns the merged data', () => {
    const raw = loadRaw(repo({ committed: 'tracker: github\nreviewers: {sonar: {project_key: o_r}}\n', local: 'reviewers: {codex: false}\n' }));
    expect(plain(raw.data)).toEqual({ tracker: 'github', reviewers: { sonar: { project_key: 'o_r' }, codex: false } });
  });

  it.each([
    [false, false],
    [true, false],
    [false, true],
    [true, true],
  ])('reports which files exist (committed %s, local %s)', (committed, local) => {
    const raw = loadRaw(repo({ committed: committed ? 'tracker: github\n' : undefined, local: local ? 'tracker: none\n' : undefined }));
    expect([raw.hasCommitted, raw.hasLocal]).toEqual([committed, local]);
  });

  it('treats a local directory as absent', () => {
    const root = repo({});
    mkdirSync(join(root, LOCAL));
    expect(loadRaw(root).hasLocal).toBe(false);
    expect(loadConfig(root)).toEqual(resolveConfig(null));
  });

  it('reads explicit typecheck commands from the merged data', () => {
    const root = repo({ committed: 'commands: {typecheck: {python: basedpyright -p python}}\n', local: 'tracker: none\n' });
    expect(explicitTypecheck(root)).toEqual(new Set(['python']));
  });
});

describe('order of checks', () => {
  it.each([
    ['openspec: false\n', 'openspec'],
    ['reviewers: {sonar: {project_key: o_r}}\n', 'sonar'],
    ['tracker: jira\n', 'tracker'],
    ['tracker:\n', 'tracker'],
    ['reviewers: {codex: yes please}\n', 'codex'],
    ['reviewers:\n', 'reviewers'],
  ])('a local schema error names the key and the local file: %j', (text, key) => {
    const root = repo({ local: text });
    const error = configError(root);
    expect(error.startsWith(`${join(root, LOCAL)}: `)).toBe(true);
    expect(error).toContain(key);
  });

  it('checks the committed YAML before the local YAML', () => {
    const root = repo({ committed: 'reviewers: [\n', local: 'tracker: [\n' });
    expect(configError(root).startsWith(`${join(root, COMMITTED)}: `)).toBe(true);
  });

  it('names the local file for invalid local YAML', () => {
    const root = repo({ committed: 'tracker: github\n', local: 'tracker: [\n' });
    expect(configError(root).startsWith(`${join(root, LOCAL)}: `)).toBe(true);
  });

  it.each(['- tracker\n', '42\n'])('requires a local mapping: %j', (text) => {
    const root = repo({ local: text });
    expect(configError(root).startsWith(`${join(root, LOCAL)}: `)).toBe(true);
  });

  it('checks the local schema before the committed schema', () => {
    const root = repo({ committed: 'bogus: 1\n', local: 'openspec: false\n' });
    expect(configError(root).startsWith(`${join(root, LOCAL)}: `)).toBe(true);
  });

  it.each(['bogus: 1\n', '- a\n'])('names the committed file for its own error under a valid local file: %j', (text) => {
    const root = repo({ committed: text, local: 'tracker: none\n' });
    expect(configError(root).startsWith(`${join(root, COMMITTED)}: `)).toBe(true);
  });
});

describe('la-config with a local file', () => {
  it('show notes each local key on stderr in schema order', () => {
    const root = repo({ committed: `format: ${currentFormat()}\ntracker: github\n`, local: 'reviewers: {codex: true}\ntracker: none\n' });
    const result = run(root, 'la-config', ['--root', root, 'show']);
    expect(result.code).toBe(0);
    expect(JSON.parse(result.out).tracker).toBe('none');
    expect(result.err).toBe(`la-config: tracker from ${LOCAL}\nla-config: reviewers.codex from ${LOCAL}\n`);
  });

  it('show reads the local file once', () => {
    const root = repo({ committed: `format: ${currentFormat()}\ntracker: github\n`, local: 'tracker: none\n' });
    vi.mocked(readFileSync).mockClear();
    expect(run(root, 'la-config', ['--root', root, 'show']).code).toBe(0);
    expect(vi.mocked(readFileSync).mock.calls.filter(([path]) => path === join(root, LOCAL))).toHaveLength(1);
  });

  it('get prints no note', () => {
    const root = repo({ committed: `format: ${currentFormat()}\ntracker: github\n`, local: 'tracker: none\n' });
    expect(run(root, 'la-config', ['--root', root, 'get', 'tracker'])).toEqual({ code: 0, out: 'none\n', err: '' });
  });
});
