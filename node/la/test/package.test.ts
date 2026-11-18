// Package invariants that need no source module: bin set, version lockstep, the root files' ignore rules, snapshot.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { describe, expect, it } from 'vitest';
import { HASH_FILE, NODE_ROOT, REPO_ROOT, SHARED, SNAPSHOT, loadYamlFile, readJson, tree } from './helpers.js';

const PACKAGE = readJson(join(NODE_ROOT, 'package.json'));
const PYTHON_SNAPSHOT = join(REPO_ROOT, 'python', 'src', 'living_architecture', 'contract', 'data');

describe('package.json', () => {
  it('has one bin per manifest command, at dist/bin/<command>.js', () => {
    const commands = Object.keys(loadYamlFile(join(SHARED, 'cli.yaml')).commands).sort();
    expect(PACKAGE.bin ?? {}).toEqual(Object.fromEntries(commands.map((c) => [c, `dist/bin/${c}.js`])));
  });

  // Provenance publishing from publish.yml fails unless this names the publishing repository.
  it('names the GitHub repository it is published from', () => {
    expect(PACKAGE.repository).toEqual({
      type: 'git',
      url: 'git+https://github.com/MotleyAI/living-architecture.git',
      directory: 'node',
    });
  });

  it('moves in lockstep with the PyPI twin and the plugin', () => {
    const pyproject = readFileSync(join(REPO_ROOT, 'python', 'pyproject.toml'), 'utf8');
    const project = pyproject.split(/^\[/m).find((section) => section.startsWith('project]')) ?? '';
    const pythonVersion = /^version = "([^"]+)"$/m.exec(project)?.[1];
    const pluginVersion = readJson(join(REPO_ROOT, 'plugin', '.claude-plugin', 'plugin.json')).version;
    expect([PACKAGE.version, PACKAGE.version]).toEqual([pythonVersion, pluginVersion]);
  });
});

describe('root README.md and LICENSE', () => {
  it.each([
    ['node/README.md', 0],
    ['node/LICENSE', 0],
    ['python/README.md', 1],
    ['python/LICENSE', 1],
  ])('git check-ignore %s exits %i', (path, status) => {
    expect(spawnSync('git', ['check-ignore', '--no-index', '-q', path], { cwd: REPO_ROOT }).status).toBe(status);
  });
});

describe('vendored files', () => {
  it('the contract snapshot is byte-identical to shared/ with modes preserved', () => {
    const current = isDeepStrictEqual(tree(SNAPSHOT), tree(SHARED));
    expect(current, 'the vendored contract snapshot is stale; run scripts/sync-shared').toBe(true);
  });

  it('the snapshot records the same contract hash as the PyPI twin', () => {
    const hash = (dir: string) => (existsSync(join(dir, HASH_FILE)) ? readFileSync(join(dir, HASH_FILE), 'utf8') : '');
    expect(hash(SNAPSHOT), 'the snapshot hash is stale; run scripts/sync-shared').toBe(hash(PYTHON_SNAPSHOT));
  });
});
