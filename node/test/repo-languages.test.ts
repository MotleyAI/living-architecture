// Repo languages: an explicit typecheck command, or a root marker plus a counted file of the language.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadConfig, repoLanguages } from '../src/config/index.js';
import { tempRepo } from './cli-run.js';

const languagesOf = (files: Record<string, string>): string[] => {
  const root = tempRepo(files);
  return repoLanguages(root, loadConfig(root));
};

describe('repoLanguages', () => {
  it('a stray script is not a language', () => {
    expect(languagesOf({ 'pyproject.toml': '', 'a.py': 'X = 1\n', 'docs/static/app.js': 'x;\n' })).toEqual(['python']);
  });

  it('typecheck null keeps the language', () => {
    const files = {
      'tsconfig.json': '{}',
      'src/a.ts': 'export {};\n',
      'living-architecture.yaml': 'commands: {typecheck: {typescript: null}}\n',
    };
    expect(languagesOf(files)).toEqual(['typescript']);
  });

  it('an explicit entry forces the language', () => {
    expect(languagesOf({ 'living-architecture.yaml': 'commands: {typecheck: {python: basedpyright -p python}}\n' })).toEqual([
      'python',
    ]);
  });

  it('lists both languages in registry order', () => {
    const files = { 'tsconfig.json': '{}', 'web/a.ts': 'export {};\n', 'setup.py': '', 'pkg/a.py': 'X = 1\n' };
    expect(languagesOf(files)).toEqual(['python', 'typescript']);
  });

  it('a marker without files is not a language', () => {
    expect(languagesOf({ 'pyproject.toml': '', 'README.md': 'x\n' })).toEqual([]);
  });

  it('exempt and ignored files do not count', () => {
    const files = {
      'tsconfig.json': '{}',
      'gen/a.ts': 'export {};\n',
      'out/b.ts': 'export {};\n',
      '.gitignore': 'out/\n',
      'living-architecture.yaml': "conventions: {exempt: ['gen/*']}\n",
    };
    expect(languagesOf(files)).toEqual([]);
  });

  it('a tracked file counts even when a later .gitignore matches it', () => {
    const root = tempRepo({ 'tsconfig.json': '{}', 'out/b.ts': 'export {};\n' });
    execFileSync('git', ['add', 'out/b.ts'], { cwd: root });
    writeFileSync(join(root, '.gitignore'), 'out/\n');
    expect(repoLanguages(root, loadConfig(root))).toEqual(['typescript']);
  });
});
