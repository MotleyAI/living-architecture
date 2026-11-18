// The npm workspace of the two packages: manifests, bins, la's pin on dr, tsconfig mapping, snapshots, split skills.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';
import { describe, expect, it } from 'vitest';
import { run, tempRepo } from './cli-run.js';
import { HASH_FILE, loadYamlFile, readJson, REPO_ROOT, tree } from '../../dr/test/helpers.js';

const PACKAGES = ['dr', 'la'] as const;
const NAMES = {
  dr: 'deterministic-refactor',
  la: 'living-architecture',
} as const;
const SHARED = join(REPO_ROOT, 'shared');
const NODE = join(REPO_ROOT, 'node');
const manifest = (pkg: string): string[] => Object.keys(loadYamlFile(join(SHARED, pkg, 'cli.yaml')).commands).sort();
const packageJson = (pkg: string): any => readJson(join(NODE, pkg, 'package.json'));
const snapshot = (pkg: string): string => join(NODE, pkg, 'src', 'contract', 'data');
const pythonSnapshot = (pkg: string): string =>
  join(
    REPO_ROOT,
    'python',
    pkg,
    'src',
    pkg === 'dr' ? 'deterministic_refactor' : 'living_architecture',
    'contract',
    'data',
  );

function series(): [string, string] {
  const [major, minor] = packageJson('la').version.split('.');
  return [`${major}.${minor}.0`, `${major}.${Number(minor) + 1}`];
}

describe('workspace root', () => {
  it('is private, lists both packages and installs no bin', () => {
    const root = readJson(join(NODE, 'package.json'));
    expect([root.private, root.workspaces, root.bin]).toEqual([true, ['dr', 'la'], undefined]);
  });
});

describe.each(PACKAGES)('node/%s/package.json', (pkg) => {
  it('is named after its package', () => {
    expect(packageJson(pkg).name).toBe(NAMES[pkg]);
  });

  it('has one bin per command of its manifest', () => {
    expect(packageJson(pkg).bin ?? {}).toEqual(Object.fromEntries(manifest(pkg).map((c) => [c, `dist/bin/${c}.js`])));
  });

  it('names the directory it is published from', () => {
    expect(packageJson(pkg).repository).toEqual({
      type: 'git',
      url: 'git+https://github.com/MotleyAI/living-architecture.git',
      directory: `node/${pkg}`,
    });
  });

  it('moves in lockstep with its PyPI twin and both plugins', () => {
    const pyproject = readFileSync(join(REPO_ROOT, 'python', pkg, 'pyproject.toml'), 'utf8');
    const project = pyproject.split(/^\[/m).find((section) => section.startsWith('project]')) ?? '';
    const versions = [
      /^version = "([^"]+)"$/m.exec(project)?.[1],
      ...PACKAGES.map((p) => readJson(join(REPO_ROOT, 'plugin', p, '.claude-plugin', 'plugin.json')).version),
    ];
    expect(versions).toEqual(versions.map(() => packageJson(pkg).version));
  });

  it('carries a snapshot of its own contract with the PyPI twin hash', () => {
    expect(isDeepStrictEqual(tree(snapshot(pkg)), tree(join(SHARED, pkg))), 'stale; run scripts/sync-shared').toBe(
      true,
    );
    const hash = (dir: string) => (existsSync(join(dir, HASH_FILE)) ? readFileSync(join(dir, HASH_FILE), 'utf8') : '');
    expect(hash(snapshot(pkg))).not.toBe('');
    expect(hash(snapshot(pkg))).toBe(hash(pythonSnapshot(pkg)));
  });
});

describe('la depends on dr', () => {
  it('pins dr to its own minor', () => {
    expect(packageJson('la').dependencies['deterministic-refactor']).toBe(`~${series()[0]}`);
    expect(packageJson('dr').dependencies?.['living-architecture']).toBeUndefined();
  });

  it('typechecks against dr sources and builds against dr declarations', () => {
    const paths = (name: string) => readJson(join(NODE, 'la', name)).compilerOptions?.paths ?? {};
    expect(paths('tsconfig.json')['deterministic-refactor']).toEqual(['../dr/src']);
    expect(readJson(join(NODE, 'la', 'tsconfig.json')).compilerOptions?.noEmit).toBe(true);
    expect(Object.keys(paths('tsconfig.build.json')).filter((key) => key.startsWith('deterministic-refactor'))).toEqual(
      [],
    );
  });
});

const LEAKS: Record<string, string[]> = loadYamlFile(join(SHARED, 'dr', 'vectors', 'skill-leaks.yaml')) ?? {};
const LANGUAGES = Object.keys(loadYamlFile(join(SHARED, 'dr', 'languages.yaml')));
const skills = (pkg: string): string[] => {
  const dir = join(REPO_ROOT, 'plugin', pkg, 'skills');
  return existsSync(dir)
    ? readdirSync(dir)
        .filter((name) => existsSync(join(dir, name, 'SKILL.md')))
        .sort()
    : [];
};
const skillText = (pkg: string, name: string): string =>
  readFileSync(join(REPO_ROOT, 'plugin', pkg, 'skills', name, 'SKILL.md'), 'utf8');
const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const ALL_SKILLS = PACKAGES.flatMap((pkg) => skills(pkg).map((name) => [pkg, name] as const));

describe('split skills', () => {
  it('both plugins have skills', () => {
    expect(PACKAGES.map((pkg) => skills(pkg).length > 0)).toEqual([true, true]);
  });

  it.each(ALL_SKILLS)('%s:%s names no language-only token', (pkg, name) => {
    const tokens = [...new Set(Object.values(LEAKS).flat())].sort();
    expect(tokens.filter((token) => new RegExp(`(?<!\\w)${escape(token)}(?!\\w)`).test(skillText(pkg, name)))).toEqual(
      [],
    );
  });

  it.each(ALL_SKILLS.filter(([pkg]) => pkg === 'dr'))('%s:%s names only valid dr-config keys', (pkg, name) => {
    const root = tempRepo({});
    const text = skillText(pkg, name);
    expect([...text.matchAll(/la-config get /g)]).toEqual([]);
    const keys = [
      ...new Set([...text.matchAll(/dr-config get ([A-Za-z0-9_.<>-]*[A-Za-z0-9_>])/g)].map((m) => m[1] ?? '')),
    ];
    const invalid = keys.filter((key) =>
      (key.includes('<language>') ? LANGUAGES.map((l) => key.replaceAll('<language>', l)) : [key]).some(
        (k) => run(root, 'dr-config', ['get', k]).code !== 0,
      ),
    );
    expect(invalid).toEqual([]);
  });

  it('dr-config refuses an la key', () => {
    expect(run(tempRepo({}), 'dr-config', ['get', 'tracker']).code).toBe(2);
    expect(run(tempRepo({}), 'dr-config', ['get', 'exempt']).code).toBe(0);
  });
});
