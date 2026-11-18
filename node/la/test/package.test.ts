// Package invariants that need no source module, per package: bin set, version lockstep, the packed root files'
// ignore rules, snapshot.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { describe, expect, it } from 'vitest';
import { HASH_FILE, NODE_ROOT, REPO_ROOT, SHARED, loadYamlFile, readJson, tree } from '../../dr/test/helpers.js';

const PACKAGES = ['dr', 'la'] as const;
const packageJson = (pkg: string): any => readJson(join(NODE_ROOT, pkg, 'package.json'));
// Each package's contract snapshot and its PyPI twin's; la has none of its own until its contract splits off dr's.
const SNAPSHOTS: [string, string][] = [
  [join(NODE_ROOT, 'dr', 'src', 'contract', 'data'), join(REPO_ROOT, 'python', 'dr', 'src', 'deterministic_refactor', 'contract', 'data')],
];

describe.each(PACKAGES)('node/%s/package.json', (pkg) => {
  it('has one bin per command of its package, at dist/bin/<command>.js', () => {
    const commands = Object.keys(loadYamlFile(join(SHARED, 'cli.yaml')).commands)
      .filter((c) => c.startsWith(`${pkg}-`))
      .sort();
    expect(packageJson(pkg).bin ?? {}).toEqual(Object.fromEntries(commands.map((c) => [c, `dist/bin/${c}.js`])));
  });

  // Provenance publishing from publish.yml fails unless this names the publishing repository.
  it('names the GitHub repository it is published from', () => {
    expect(packageJson(pkg).repository).toEqual({
      type: 'git',
      url: 'git+https://github.com/MotleyAI/living-architecture.git',
      directory: `node/${pkg}`,
    });
  });

  it('moves in lockstep with its PyPI twin and the plugin', () => {
    const pyproject = readFileSync(join(REPO_ROOT, 'python', pkg, 'pyproject.toml'), 'utf8');
    const project = pyproject.split(/^\[/m).find((section) => section.startsWith('project]')) ?? '';
    const pythonVersion = /^version = "([^"]+)"$/m.exec(project)?.[1];
    const pluginVersion = readJson(join(REPO_ROOT, 'plugin', '.claude-plugin', 'plugin.json')).version;
    expect([packageJson(pkg).version, packageJson(pkg).version]).toEqual([pythonVersion, pluginVersion]);
  });
});

describe('packed README.md and LICENSE', () => {
  it.each([
    ['node/dr/README.md', 0],
    ['node/dr/LICENSE', 0],
    ['node/la/README.md', 0],
    ['node/la/LICENSE', 0],
    ['python/dr/README.md', 1],
    ['python/dr/LICENSE', 1],
    ['python/la/README.md', 1],
    ['python/la/LICENSE', 1],
  ])('git check-ignore %s exits %i', (path, status) => {
    expect(spawnSync('git', ['check-ignore', '--no-index', '-q', path], { cwd: REPO_ROOT }).status).toBe(status);
  });
});

describe.each(SNAPSHOTS)('vendored contract %s', (snapshot, pythonSnapshot) => {
  it('is byte-identical to shared/ with modes preserved', () => {
    const current = isDeepStrictEqual(tree(snapshot), tree(SHARED));
    expect(current, 'the vendored contract snapshot is stale; run scripts/sync-shared').toBe(true);
  });

  it('records the same contract hash as the PyPI twin', () => {
    const hash = (dir: string) => (existsSync(join(dir, HASH_FILE)) ? readFileSync(join(dir, HASH_FILE), 'utf8') : '');
    expect(hash(snapshot), 'the snapshot hash is stale; run scripts/sync-shared').toBe(hash(pythonSnapshot));
  });
});
