// Skills are language-neutral: no language-only token (shared/vectors/skill-leaks.yaml) and only valid
// `la-config get` keys, `<language>` standing for every registered language.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { run, tempRepo } from './cli-run.js';
import { REPO_ROOT, SHARED, loadYamlFile, vectors } from './helpers.js';

const SKILLS_DIR = join(REPO_ROOT, 'plugin', 'skills');
const SKILLS = readdirSync(SKILLS_DIR).filter((name) => existsSync(join(SKILLS_DIR, name, 'SKILL.md'))).sort();
const LEAKS: Record<string, string[]> = vectors('skill-leaks.yaml') ?? {};
const LANGUAGES = Object.keys(loadYamlFile(join(SHARED, 'languages.yaml')));
const CONFIG_GET = /la-config get ([A-Za-z0-9_.<>-]*[A-Za-z0-9_>])/g;

const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const skillText = (name: string): string => readFileSync(join(SKILLS_DIR, name, 'SKILL.md'), 'utf8');

function leaks(text: string): string[] {
  const tokens = [...new Set(Object.values(LEAKS).flat())].sort();
  return tokens.filter((token) => new RegExp(`(?<!\\w)${escape(token)}(?!\\w)`).test(text));
}

function invalidKeys(text: string): string[] {
  const root = tempRepo({});
  const keys = [...new Set([...text.matchAll(CONFIG_GET)].map((m) => m[1] ?? ''))].sort();
  return keys.filter((key) => {
    const concrete = key.includes('<language>') ? LANGUAGES.map((lang) => key.replaceAll('<language>', lang)) : [key];
    return concrete.some((k) => run(root, 'la-config', ['get', k]).code !== 0);
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

  it.each(SKILLS)('%s names no language-only token', (name) => {
    expect(leaks(skillText(name))).toEqual([]);
  });
});

describe('la-config keys in skills', () => {
  it('flags an unknown key', () => {
    expect(invalidKeys('`la-config get lang.<language>.runner`')).toEqual(['lang.<language>.runner']);
    expect(invalidKeys('`la-config get languages` and `la-config get lang.<language>.markers`')).toEqual([]);
  });

  it.each(SKILLS)('%s names only valid keys', (name) => {
    expect(invalidKeys(skillText(name))).toEqual([]);
  });
});

describe('language idioms', () => {
  it.each(LANGUAGES)('plugin/languages/%s.md exists', (language) => {
    expect(existsSync(join(REPO_ROOT, 'plugin', 'languages', `${language}.md`))).toBe(true);
  });
});
