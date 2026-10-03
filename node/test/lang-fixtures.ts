// Materialize a conformance case's TypeScript repo (fixture and case overlays, removes, symlinks) in a temp dir.
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { parse } from 'yaml';
import type { TsLayout } from '../src/lang/index.js';
import { REPO_ROOT } from './helpers.js';

const CORPUS = join(REPO_ROOT, 'conformance');

export function materialize(caseName: string): TsLayout {
  const caseDir = join(CORPUS, 'cases', caseName);
  const spec = parse(readFileSync(join(caseDir, 'case.yaml'), 'utf8'));
  const repo = join(mkdtempSync(join(tmpdir(), 'la-lang-')), 'repo');
  mkdirSync(repo);
  const bases = [...(spec.fixture ? [join(CORPUS, 'fixtures', spec.fixture)] : []), caseDir];
  for (const base of bases) {
    for (const sub of ['repo', 'node']) {
      if (existsSync(join(base, sub))) cpSync(join(base, sub), repo, { recursive: true, verbatimSymlinks: true });
    }
  }
  for (const rel of spec.remove ?? []) rmSync(join(repo, rel), { recursive: true, force: true });
  for (const [link, target] of Object.entries<string>(spec.symlinks ?? {})) {
    mkdirSync(dirname(join(repo, link)), { recursive: true });
    symlinkSync(target, join(repo, link));
  }
  const section = parse(readFileSync(join(repo, 'architecture', 'index.yaml'), 'utf8')).typescript;
  return {
    repoRoot: repo,
    sourceRoot: section.source_root ? join(repo, section.source_root) : repo,
    rootPackage: section.root_package,
    tsconfig: section.tsconfig ?? null,
  };
}

export function cleanup(layout: TsLayout): void {
  rmSync(dirname(layout.repoRoot), { recursive: true, force: true });
}
