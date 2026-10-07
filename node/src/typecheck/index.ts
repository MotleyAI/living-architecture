// `la-typecheck`: each applicable language's checker against its committed, only-shrinking baseline.
import { accessSync, constants, existsSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { ConfigError, findRepoRoot, type LaConfig, loadConfig, repoLanguages } from '../config/index.js';
import { language, message, whichPath } from '../contract/index.js';
import { checkTypescript } from '../lang/index.js';
import * as twin from '../twin/index.js';

type Lang = 'python' | 'typescript';

/** The checker cannot be run; the message is printed, exit 2. */
class CommandError extends Error {}

const err = (text: string): void => void process.stderr.write(`${text}\n`);

/** POSIX shell words without expansion, as Python's shlex.split (shared/vectors/command-split.yaml); throws when malformed. */
export function splitCommand(text: string): string[] {
  const words: string[] = [];
  let word: string | null = null;
  let i = 0;
  const append = (ch: string): void => {
    word = (word ?? '') + ch;
  };
  while (i < text.length) {
    const ch = text[i++] ?? '';
    if (' \t\r\n'.includes(ch)) {
      if (word !== null) words.push(word);
      word = null;
    } else if (ch === "'") {
      const end = text.indexOf("'", i);
      if (end === -1) throw new Error('No closing quotation');
      append(text.slice(i, end));
      i = end + 1;
    } else if (ch === '"') {
      append('');
      for (;;) {
        if (i >= text.length) throw new Error('No closing quotation');
        const c = text[i++] ?? '';
        if (c === '"') break;
        if (c === '\\' && (text[i] === '"' || text[i] === '\\')) append(text[i++] ?? '');
        else append(c);
      }
    } else if (ch === '\\') {
      if (i >= text.length) throw new Error('No escaped character');
      append(text[i++] ?? '');
    } else {
      append(ch);
    }
  }
  if (word !== null) words.push(word);
  return words;
}

export function combinedExit(codes: number[]): number {
  return Math.max(0, ...codes);
}

const commandOf = (config: LaConfig, id: string): string | null => config.commands.typecheck[id as Lang] ?? null;

/** The repo languages whose typecheck command is not `null`. */
export function applicable(root: string, config: LaConfig): string[] {
  return repoLanguages(root, config).filter((id) => commandOf(config, id) !== null);
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

function checkNative(root: string, command: string, write: boolean): number {
  let argv: string[];
  try {
    argv = resolveArgv(root, twin.NATIVE_LANGUAGE, command);
  } catch (error) {
    if (!(error instanceof CommandError)) throw error;
    err(error.message);
    return 2;
  }
  return checkTypescript({ repoRoot: root, argv, command, baseline: language(twin.NATIVE_LANGUAGE).baseline_file, write });
}

function check(root: string, id: string, command: string, write: boolean): number {
  if (id === twin.NATIVE_LANGUAGE) return checkNative(root, command, write);
  try {
    return twin.runLanguage('la-typecheck', id, write ? ['--write-baseline'] : [], root, root);
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    err(message('typecheck.error', { error: error.message }));
    return 2;
  }
}

function setup(cwd: string): [string, LaConfig] | number {
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

/** `la-typecheck`; with `languageId` (the twins' protocol) only that native language, without a header. */
export function run(cwd: string, write: boolean, languageId: string | null): number {
  const ready = setup(cwd);
  if (typeof ready === 'number') return ready;
  const [root, config] = ready;
  if (languageId !== null) {
    if (languageId !== twin.NATIVE_LANGUAGE) {
      err(message('typecheck.error', { error: message('typecheck.not-native', { language: languageId }) }));
      return 2;
    }
    return checkNative(root, commandOf(config, languageId) ?? '', write);
  }
  let languages: string[];
  try {
    languages = applicable(root, config);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    err(message('typecheck.error', { error: error.message }));
    return 2;
  }
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
    codes.push(check(root, id, command, write));
  }
  if (write && codes.length === 0) {
    err(message('typecheck.refusal'));
    return 2;
  }
  return combinedExit(codes);
}
