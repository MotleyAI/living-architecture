// Routing files to their language and collecting each language's conventions facts, natively or from its twin.
import { readFileSync } from 'node:fs';
import { contractHash, language, languageIds, message } from '../contract/index.js';
import { VERSION } from '../index.js';
import { conventionsFacts } from '../lang/index.js';
import * as twin from '../twin/index.js';

export type Facts = Record<string, any>;

/** The facts of another language could not be had; the message (if any) is printed, exit 2. */
export class FactsError extends Error {}

/** The registry language whose source extensions contain the path's extension, else null. */
export function languageOf(path: string): string | null {
  for (const id of languageIds()) {
    if ((language(id).source_extensions as string[]).some((ext) => path.endsWith(ext))) return id;
  }
  return null;
}

/** Known-extension paths grouped by language, each in input order. */
function byLanguage(paths: string[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const path of paths) {
    const id = languageOf(path);
    if (id !== null) out.set(id, [...(out.get(id) ?? []), path]);
  }
  return out;
}

/** Facts entry per path (all with a known extension, relative to `cwd`); FactsError when a twin fails. */
export function collect(paths: string[], cwd: string, repoRoot: string): Map<string, Facts> {
  const out = new Map<string, Facts>();
  for (const [id, group] of byLanguage(paths)) {
    let entries: Facts[];
    if (id === twin.NATIVE_LANGUAGE) {
      entries = conventionsFacts(cwd, group);
    } else {
      try {
        entries = twin.requestConventionsFacts(id, cwd, group, repoRoot);
      } catch (error) {
        if (error instanceof twin.RelayedFailure) throw new FactsError('');
        if (error instanceof twin.TwinError) throw new FactsError(error.message);
        throw error;
      }
    }
    for (const entry of entries) out.set(entry.path, entry);
  }
  return out;
}

function stdinPaths(): string[] | null {
  try {
    const paths: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(0)));
    return Array.isArray(paths) && paths.every((p) => typeof p === 'string') ? paths : null;
  } catch {
    return null;
  }
}

/** The facts server: the stdin JSON path list's facts document on stdout; only the native language. */
export function emit(lang: string, cwd: string): number {
  const fail = (error: string): number => {
    process.stderr.write(`${message('conventions.error', { error })}\n`);
    return 2;
  };
  if (lang !== twin.NATIVE_LANGUAGE) return fail(message('twin.not-native', { language: lang }));
  const paths = stdinPaths();
  if (paths === null) return fail(message('conventions.facts-stdin-invalid'));
  const document = { language: lang, version: VERSION, contract_hash: contractHash(), files: conventionsFacts(cwd, paths) };
  process.stdout.write(`${JSON.stringify(document)}\n`);
  return 0;
}
