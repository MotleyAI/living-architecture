// `trmv-typecheck`: each applicable language's checker against its committed, only-shrinking baseline, or in stealth
// mode against the checker's errors at the merge base.
import { accessSync, constants, existsSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { defaultBaseRef, isCommit, mergeBase, resolveBaseRef, trackedAtHead } from '../changes/index.js';
import {
  ConfigError,
  type TrmvConfig,
  findRepoRoot,
  isStealth,
  languageSettings,
  loadConfig,
  repoLanguages,
  stealthDir,
} from '../config/index.js';
import { language, message, whichPath } from '../contract/index.js';
import { VERSION } from '../index.js';
import { type BaselineCounts, CheckoutError, checkTypescript, parseBaseline, renderBaseline, tscCounts, withMergeBaseCheckout } from '../lang/index.js';
import * as twin from '../twin/index.js';
import { cacheKey, fingerprints, readEntry, writeEntry } from './cache.js';

export { cacheKey } from './cache.js';

/** A stealth run: the raw `--base` to hand another twin, and the merge-base commit, once one is needed. */
interface Stealth {
  base: string | null;
  commit: string | null;
}

type Lang = 'python' | 'typescript';

/** The checker cannot be run; the message is printed, exit 2. */
class CommandError extends Error {}

const err = (text: string): void => void process.stderr.write(`${text}\n`);

type Part = [text: string, next: number];

function singleQuoted(text: string, start: number): Part {
  const end = text.indexOf("'", start);
  if (end === -1) throw new Error('No closing quotation');
  return [text.slice(start, end), end + 1];
}

function doubleQuoted(text: string, start: number): Part {
  let out = '';
  let i = start;
  for (;;) {
    if (i >= text.length) throw new Error('No closing quotation');
    const c = text[i++] ?? '';
    if (c === '"') return [out, i];
    const escapes = c === '\\' && (text[i] === '"' || text[i] === '\\');
    out += escapes ? (text[i++] ?? '') : c;
  }
}

function escaped(text: string, start: number): Part {
  if (start >= text.length) throw new Error('No escaped character');
  return [text[start] ?? '', start + 1];
}

/** POSIX shell words without expansion, as Python's shlex.split (shared/vectors/command-split.yaml); throws when malformed. */
export function splitCommand(text: string): string[] {
  const words: string[] = [];
  let word: string | null = null;
  let i = 0;
  while (i < text.length) {
    const ch = text[i++] ?? '';
    if (' \t\r\n'.includes(ch)) {
      if (word !== null) words.push(word);
      word = null;
      continue;
    }
    let part = ch;
    if (ch === "'") [part, i] = singleQuoted(text, i);
    else if (ch === '"') [part, i] = doubleQuoted(text, i);
    else if (ch === '\\') [part, i] = escaped(text, i);
    word = (word ?? '') + part;
  }
  if (word !== null) words.push(word);
  return words;
}

export function combinedExit(codes: number[]): number {
  return Math.max(0, ...codes);
}

const commandOf = (config: TrmvConfig, id: string): string | null => config.commands.typecheck[id as Lang] ?? null;

/** The repo languages whose typecheck command is not `null`. */
export function applicable(root: string, config: TrmvConfig): string[] {
  return repoLanguages(root, languageSettings(root)).filter((id) => commandOf(config, id) !== null);
}

function executable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

/** The command's words with its first one resolved: a path from the repo root, else local bin dir, then PATH. */
function resolveArgv(root: string, id: string, command: string): string[] {
  let words: string[];
  try {
    words = splitCommand(command);
  } catch {
    words = [];
  }
  const [first, ...rest] = words;
  if (first === undefined) throw new CommandError(message('typecheck.bad-command', { language: id, command }));
  const localBin: string = language(id).local_bin;
  let found: string | null;
  if (first.includes('/')) found = executable(resolve(root, first)) ? resolve(root, first) : null;
  else found = executable(join(root, localBin, first)) ? join(root, localBin, first) : whichPath(first);
  if (found === null) throw new CommandError(message('typecheck.not-found', { language: id, command: first, local_bin: localBin }));
  return [found, ...rest];
}

function mergeBaseFailed(id: string, command: string, commit: string): number {
  err(message('typecheck.merge-base-failed', { language: id, command, commit: commit.slice(0, 7) }));
  return 2;
}

/** The TypeScript baseline counts of the checker's errors at `commit`, from the cache or a temporary checkout; the exit
 * code when the checker fails there. */
/** tsc's counts at `commit`, from a temporary checkout; null when the checker or the checkout fails there. */
function typescriptCheckedOut(root: string, command: string, commit: string): BaselineCounts | null {
  try {
    return withMergeBaseCheckout(root, commit, language('typescript').environment_dirs as string[], (checkout) => {
      let argv: string[];
      try {
        argv = resolveArgv(checkout, 'typescript', command);
      } catch (error) {
        if (!(error instanceof CommandError)) throw error;
        return null;
      }
      return tscCounts(checkout, argv);
    });
  } catch (error) {
    if (!(error instanceof CheckoutError)) throw error;
    return null;
  }
}

function typescriptAt(root: string, command: string, commit: string): BaselineCounts | number {
  const key = cacheKey({ commit, language: 'typescript', command, version: VERSION, fingerprints: fingerprints(root, 'typescript') });
  const directory = stealthDir(root, 'trmv');
  const entry = directory === null ? null : join(directory, 'typecheck', `${key}.json`);
  const cached = entry === null ? null : readEntry(entry);
  const parsed = cached === null ? null : parseBaseline(cached);
  if (parsed !== null) return parsed;
  const counts = typescriptCheckedOut(root, command, commit);
  if (counts === null) return mergeBaseFailed('typescript', command, commit);
  if (entry !== null) writeEntry(entry, renderBaseline(counts));
  return counts;
}

function checkNative(root: string, command: string, write: boolean, stealth: Stealth | null): number {
  let argv: string[];
  try {
    argv = resolveArgv(root, twin.NATIVE_LANGUAGE, command);
  } catch (error) {
    if (!(error instanceof CommandError)) throw error;
    err(error.message);
    return 2;
  }
  const baseline: string = language(twin.NATIVE_LANGUAGE).baseline_file;
  if (stealth !== null && !trackedAtHead(baseline, root)) {
    const base = typescriptAt(root, command, stealth.commit ?? '');
    if (typeof base === 'number') return base;
    return checkTypescript({ repoRoot: root, argv, command, baseline, write: false, base });
  }
  return checkTypescript({ repoRoot: root, argv, command, baseline, write });
}

function check(root: string, id: string, command: string, write: boolean, realignFrom: string | null, stealth: Stealth | null): number {
  if (id === twin.NATIVE_LANGUAGE) return checkNative(root, command, write, stealth);
  const args: string[] = [];
  if (write) args.push('--write-baseline');
  else if (realignFrom !== null) args.push('--realign-from', realignFrom);
  if (stealth?.base) args.push('--base', stealth.base);
  try {
    return twin.runLanguage('trmv-typecheck', id, args, root, root);
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    err(message('typecheck.error', { error: error.message }));
    return 2;
  }
}

function setup(cwd: string): [string, TrmvConfig] | number {
  const root = findRepoRoot(cwd);
  if (!existsSync(join(root, '.git'))) {
    err(message('typecheck.not-git'));
    return 2;
  }
  try {
    return [root, loadConfig(root)];
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    err(message('typecheck.error', { error: error.message }));
    return 2;
  }
}

function checkOnly(root: string, config: TrmvConfig, languageId: string, write: boolean, stealth: Stealth | null): number {
  if (languageId !== twin.NATIVE_LANGUAGE) {
    err(message('typecheck.error', { error: message('typecheck.not-native', { language: languageId }) }));
    return 2;
  }
  return checkNative(root, commandOf(config, languageId) ?? '', write, stealth);
}

function checkAll(
  root: string,
  config: TrmvConfig,
  languages: string[],
  write: boolean,
  realignFrom: string | null,
  stealth: Stealth | null,
): number {
  if (languages.length === 0) {
    err(message('typecheck.no-languages'));
    return 0;
  }
  const codes: number[] = [];
  for (const id of languages) {
    const command = commandOf(config, id) ?? '';
    err(message('typecheck.header', { language: id, command }));
    const baseline: string = language(id).baseline_file;
    if (write && existsSync(join(root, baseline))) {
      err(message('typecheck.skip', { language: id, baseline }));
      continue;
    }
    codes.push(check(root, id, command, write, realignFrom, stealth));
  }
  if (write && codes.length === 0) {
    err(message('typecheck.refusal'));
    return 2;
  }
  return combinedExit(codes);
}

/** The merge base of the base ref (`--base`, else origin/HEAD's target) and HEAD; the exit code when none. */
function mergeBaseOf(root: string, base: string | null): string | number {
  const ref = base !== null ? resolveBaseRef(base, root) : defaultBaseRef(root);
  if (ref === null) {
    err(message('typecheck.stealth-no-base'));
    return 2;
  }
  return mergeBase(ref, root);
}

/** The stealth run, null outside stealth mode; the exit code of a stealth refusal. */
function stealthRun(root: string, languages: string[], write: boolean, realignFrom: string | null, base: string | null): Stealth | number | null {
  if (!isStealth(root)) return null;
  if (write) {
    err(message('typecheck.stealth-write-refused'));
    return 2;
  }
  const untracked = languages.filter((id) => !trackedAtHead(language(id).baseline_file as string, root));
  if (realignFrom !== null && untracked.includes('python')) {
    err(message('typecheck.stealth-realign-refused'));
    return 2;
  }
  if (untracked.length === 0) return { base, commit: null };
  const commit = mergeBaseOf(root, base);
  return typeof commit === 'number' ? commit : { base, commit };
}

/**
 * `trmv-typecheck`; with `languageId` (the twins' protocol) only that native language, without a header. `realignFrom`
 * goes to the Python section, whose baseline alone has positions; in stealth mode, `base` names the branch whose merge
 * base gives the baseline of each language the repo tracks none for.
 */
export function run(cwd: string, write: boolean, languageId: string | null, realignFrom: string | null = null, base: string | null = null): number {
  const ready = setup(cwd);
  if (typeof ready === 'number') return ready;
  const [root, config] = ready;
  let languages: string[];
  let stealth: Stealth | number | null;
  let known: boolean;
  try {
    known = realignFrom === null || isCommit(realignFrom, root);
    languages = languageId !== null ? [languageId] : applicable(root, config);
    stealth = known ? stealthRun(root, languages, write, realignFrom, base) : null;
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    err(message('typecheck.error', { error: error.message }));
    return 2;
  }
  if (!known) {
    err(message('typecheck.bad-ref', { ref: realignFrom ?? '' }));
    return 2;
  }
  if (typeof stealth === 'number') return stealth;
  if (languageId !== null) return checkOnly(root, config, languageId, write, stealth);
  return checkAll(root, config, languages, write, realignFrom, stealth);
}
