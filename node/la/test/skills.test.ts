// Skills are language-neutral: no language-only token (shared/dr/vectors/skill-leaks.yaml) and only valid
// `la-config get` / `dr-config get` keys, `<language>` standing for every registered language.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { run, tempRepo } from './cli-run.js';
import { REPO_ROOT, SHARED, loadYamlFile, vectors } from '../../dr/test/helpers.js';

const PLUGIN_ROOT = join(REPO_ROOT, 'plugin');
const SKILLS = ['dr', 'la']
  .flatMap((pkg) => {
    const dir = join(PLUGIN_ROOT, pkg, 'skills');
    return readdirSync(dir)
      .filter((name) => existsSync(join(dir, name, 'SKILL.md')))
      .map((name) => `${pkg}:${name}`);
  })
  .sort();
const LEAKS: Record<string, string[]> = vectors('skill-leaks.yaml') ?? {};
const LANGUAGES = Object.keys(loadYamlFile(join(SHARED, 'languages.yaml')));
const CONFIG_GET = /\b((?:la|dr)-config) get ([A-Za-z0-9_.<>-]*[A-Za-z0-9_>])/g;

const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const skillText = (id: string): string => {
  const [pkg, name] = id.split(':') as [string, string];
  return readFileSync(join(PLUGIN_ROOT, pkg, 'skills', name, 'SKILL.md'), 'utf8');
};

function leaks(text: string): string[] {
  const tokens = [...new Set(Object.values(LEAKS).flat())].sort();
  return tokens.filter((token) => new RegExp(`(?<!\\w)${escape(token)}(?!\\w)`).test(text));
}

function invalidKeys(text: string): string[] {
  const root = tempRepo({});
  const uses = [...new Set([...text.matchAll(CONFIG_GET)].map((m) => `${m[1]} get ${m[2]}`))].sort();
  return uses.filter((use) => {
    const [command, , key] = use.split(' ') as [string, string, string];
    const concrete = key.includes('<language>') ? LANGUAGES.map((lang) => key.replaceAll('<language>', lang)) : [key];
    return concrete.some((k) => run(root, command, ['get', k]).code !== 0);
  });
}

describe('skill leaks', () => {
  it('has tokens for every language', () => {
    expect(Object.keys(LEAKS).sort()).toEqual([...LANGUAGES].sort());
  });

  it('matches whole tokens only', () => {
    expect(leaks('run basedpyright, then `*.py` files')).toEqual(['*.py', 'basedpyright']);
    expect(leaks('europe tscx jester')).toEqual([]);
  });

  it.each(SKILLS)('%s names no language-only token', (id) => {
    expect(leaks(skillText(id))).toEqual([]);
  });
});

describe('config keys in skills', () => {
  it('flags an unknown key', () => {
    expect(invalidKeys('`la-config get lang.<language>.runner`')).toEqual(['la-config get lang.<language>.runner']);
    expect(invalidKeys('`dr-config get tracker`')).toEqual(['dr-config get tracker']);
    expect(invalidKeys('`la-config get languages` and `dr-config get lang.<language>.markers`')).toEqual([]);
  });

  it.each(SKILLS)('%s names only valid keys', (id) => {
    expect(invalidKeys(skillText(id))).toEqual([]);
  });
});

describe('language idioms', () => {
  it.each(LANGUAGES)('plugin/dr/languages/%s.md exists', (language) => {
    expect(existsSync(join(PLUGIN_ROOT, 'dr', 'languages', `${language}.md`))).toBe(true);
  });
});
