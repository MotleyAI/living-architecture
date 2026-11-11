// `la-affected-tests`: the changed tests plus every test whose imports reach a changed file, each language from its twin.
import { lstatSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { changedPathBytes, repoPathBytes, resolveBaseRef } from '../changes/index.js';
import { ConfigError, findRepoRoot } from '../config/index.js';
import {
  byCodePoint,
  contractHash,
  decodeUtf8OrNull,
  isTestFile,
  language,
  languageIds,
  languageOf,
  message,
  schema,
  validate,
} from '../contract/index.js';
import { VERSION } from '../index.js';
import { dependencyEdges, LangError } from '../lang/index.js';
import * as twin from '../twin/index.js';

export interface Change {
  path: string;
  deleted: boolean;
}

/** A failure already worded for stderr (empty: the other twin's stderr was relayed). */
class AffectedError extends Error {}

const exists = (path: string): boolean => {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
};

const hasExtension = (path: string, lang: string): boolean =>
  (language(lang).source_extensions as string[]).some((ext) => path.endsWith(ext));

/** The path as text; AffectedError naming it when it is not UTF-8 or holds a line break. */
function representable(path: Buffer): string {
  const text = decodeUtf8OrNull(path);
  if (text === null || /[\n\r]/.test(text)) {
    throw new AffectedError(message('affected.unrepresentable-path', { path: path.toString('utf8') }));
  }
  return text;
}

/** Existing repo files of `lang`, in byte order; unrepresentable ones refused. */
function repoFiles(repoRoot: string, lang: string): string[] {
  return repoPathBytes(repoRoot)
    .filter((path) => hasExtension(path.toString('utf8'), lang))
    .map(representable)
    .filter((path) => exists(join(repoRoot, path)));
}

/** `lang`'s tests: changed ones and those whose imports reach a changed file. */
function selection(repoRoot: string, lang: string, changes: Change[]): string[] {
  const files = repoFiles(repoRoot, lang);
  const deleted = changes.filter((c) => c.deleted && hasExtension(c.path, lang)).map((c) => c.path);
  const nonSource = language(lang).imports_non_source === true;
  const starts = changes.filter((c) => hasExtension(c.path, lang) || (nonSource && languageOf(c.path) === null)).map((c) => c.path);
  const importers = new Map<string, string[]>();
  for (const [src, dst] of dependencyEdges(repoRoot, files, [...deleted].sort(byCodePoint))) {
    importers.set(dst, [...(importers.get(dst) ?? []), src]);
  }
  const reached = new Set(starts);
  const queue = [...starts];
  for (let path = queue.shift(); path !== undefined; path = queue.shift()) {
    for (const importer of importers.get(path) ?? []) {
      if (!reached.has(importer)) {
        reached.add(importer);
        queue.push(importer);
      }
    }
  }
  const gone = new Set(deleted);
  return [...reached].filter((path) => !gone.has(path) && languageOf(path) === lang && isTestFile(path)).sort(byCodePoint);
}

/** The languages to compute: those with a changed file, and those importing non-source files when one changed. */
function computed(repoRoot: string, changes: Change[]): string[] {
  const nonSourceChanged = changes.some((c) => languageOf(c.path) === null);
  return languageIds().filter(
    (lang) =>
      changes.some((c) => hasExtension(c.path, lang)) ||
      (language(lang).imports_non_source === true &&
        nonSourceChanged &&
        repoPathBytes(repoRoot).some((p) => hasExtension(p.toString('utf8'), lang) && exists(join(repoRoot, p.toString('utf8'))))),
  );
}

function languageTests(repoRoot: string, lang: string, changes: Change[]): string[] {
  if (lang === twin.NATIVE_LANGUAGE) return selection(repoRoot, lang, changes);
  try {
    return twin.requestAffected(lang, changes, repoRoot);
  } catch (error) {
    if (error instanceof twin.RelayedFailure) throw new AffectedError('');
    if (error instanceof twin.TwinError) throw new AffectedError(error.message);
    throw error;
  }
}

function fail(error: unknown): number {
  if (error instanceof AffectedError || error instanceof ConfigError || error instanceof LangError) {
    if (error.message) process.stderr.write(`${message('affected.error', { error: error.message })}\n`);
    return 2;
  }
  throw error;
}

/** Print the affected test files of the change against `origin/<base>`, one per line in code-point order. */
export function run(cwd: string, base: string): number {
  const repoRoot = findRepoRoot(cwd);
  let tests: string[];
  try {
    const baseRef = resolveBaseRef(base, repoRoot);
    const paths = changedPathBytes({ baseRef, repoRoot, deletions: true, untracked: true }).map(representable);
    const changes = paths.map((path) => ({ path, deleted: !exists(join(repoRoot, path)) })).sort((a, b) => byCodePoint(a.path, b.path));
    tests = computed(repoRoot, changes).flatMap((lang) => languageTests(repoRoot, lang, changes));
  } catch (error) {
    return fail(error);
  }
  const lines = [...new Set(tests)].sort(byCodePoint);
  if (lines.length > 0) process.stdout.write(`${lines.join('\n')}\n`);
  return 0;
}

function stdinChanges(): Change[] | null {
  try {
    const document: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(0)));
    return validate(schema('affected-request'), document).length === 0 ? (document as { changes: Change[] }).changes : null;
  } catch {
    return null;
  }
}

/** The internal request: the stdin change set's selection of the native language as a JSON document. */
export function serve(cwd: string, lang: string): number {
  if (lang !== twin.NATIVE_LANGUAGE) return fail(new AffectedError(message('twin.not-native', { language: lang })));
  const changes = stdinChanges();
  if (changes === null) return fail(new AffectedError(message('affected.request-invalid')));
  let tests: string[];
  try {
    tests = selection(findRepoRoot(cwd), lang, changes);
  } catch (error) {
    return fail(error);
  }
  const document = { language: lang, version: VERSION, contract_hash: contractHash(), tests };
  process.stdout.write(`${JSON.stringify(document)}\n`);
  return 0;
}
