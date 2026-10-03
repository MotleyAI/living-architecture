// Package invariants that need no source module: bin set, version lockstep, vendored root files and snapshot.
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

  it('moves in lockstep with the PyPI twin and the plugin', () => {
    const pyproject = readFileSync(join(REPO_ROOT, 'python', 'pyproject.toml'), 'utf8');
    const project = pyproject.split(/^\[/m).find((section) => section.startsWith('project]')) ?? '';
    const pythonVersion = /^version = "([^"]+)"$/m.exec(project)?.[1];
    const pluginVersion = readJson(join(REPO_ROOT, 'plugin', '.claude-plugin', 'plugin.json')).version;
    expect([PACKAGE.version, PACKAGE.version]).toEqual([pythonVersion, pluginVersion]);
  });
});

describe('vendored files', () => {
  it.each(['README.md', 'LICENSE'])('%s equals the root copy', (name) => {
    const copy = join(NODE_ROOT, name);
    const current = existsSync(copy) && readFileSync(copy).equals(readFileSync(join(REPO_ROOT, name)));
    expect(current, `node/${name} is stale; run scripts/sync-shared`).toBe(true);
  });

  it('the contract snapshot is byte-identical to shared/ with modes preserved', () => {
    const current = isDeepStrictEqual(tree(SNAPSHOT), tree(SHARED));
    expect(current, 'the vendored contract snapshot is stale; run scripts/sync-shared').toBe(true);
  });

  it('the snapshot records the same contract hash as the PyPI twin', () => {
    const hash = (dir: string) => (existsSync(join(dir, HASH_FILE)) ? readFileSync(join(dir, HASH_FILE), 'utf8') : '');
    expect(hash(SNAPSHOT), 'the snapshot hash is stale; run scripts/sync-shared').toBe(hash(PYTHON_SNAPSHOT));
  });
});
