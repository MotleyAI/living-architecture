// Reaching the other twin: identity handshake, discovery on PATH, runner probe, forwarding, facts and language runs.
import { spawnSync, type SpawnSyncOptions, type SpawnSyncReturns } from 'node:child_process';
import { accessSync, constants, realpathSync, statSync } from 'node:fs';
import { constants as osConstants } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { contractHash, language, message, renderTemplate, schema, validate, which } from '../contract/index.js';
import { VERSION } from '../index.js';

export const NATIVE_LANGUAGE = 'typescript';
const FORWARDED_ENV = 'LA_FORWARDED';

/** The other twin cannot serve the request; the message is the hint to print. */
export class TwinError extends Error {}

/** The other twin's facts run failed; its stderr was already passed through. */
export class RelayedFailure extends Error {}

/** This twin's `la-doctor --twin` line. */
export function identity(): string {
  return `${NATIVE_LANGUAGE} ${VERSION} ${contractHash()}`;
}

const expected = (lang: string): string => `${lang} ${VERSION} ${contractHash()}`;

function hint(templateId: string, lang: string): string {
  const install = renderTemplate(language(lang).install, { version: VERSION });
  return message(templateId, { language: lang, version: VERSION, install });
}

const env = (): NodeJS.ProcessEnv => ({ ...process.env, [FORWARDED_ENV]: '1' });

/** `argv` (an `la-doctor --twin` invocation) reports `lang` at this version and contract. */
function qualifies(argv: string[], lang: string): boolean {
  const [cmd = '', ...args] = argv;
  const proc = spawnSync(cmd, args, { env: env(), encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  return proc.error === undefined && proc.status === 0 && proc.stdout.trim() === expected(lang);
}

function executable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

/** The real path of the running entry point's sibling `la-doctor.js`; null when it is not a file. */
function ownDoctor(): string | null {
  try {
    const doctor = realpathSync(join(dirname(realpathSync(process.argv[1] ?? '')), 'la-doctor.js'));
    return statSync(doctor).isFile() ? doctor : null;
  } catch {
    return null;
  }
}

function isOwn(doctor: string, own: string | null): boolean {
  try {
    return own !== null && realpathSync(doctor) === own;
  } catch {
    return false;
  }
}

/** The first directory (each real path once, never our own) whose executable `la-doctor` qualifies. */
function discoverDir(lang: string, repoRoot: string): string | null {
  const own = ownDoctor();
  const dirs = [...(process.env.PATH ?? '').split(delimiter).filter(Boolean), join(repoRoot, 'node_modules', '.bin')];
  const probed = new Set<string>();
  for (const dir of dirs) {
    let real: string;
    try {
      real = realpathSync(dir);
    } catch {
      real = dir;
    }
    if (probed.has(real)) continue;
    probed.add(real);
    const doctor = join(dir, 'la-doctor');
    if (isOwn(doctor, own)) continue;
    if (executable(doctor) && qualifies([doctor, '--twin'], lang)) return dir;
  }
  return null;
}

/** How to run one of the `lang` twin's commands; TwinError when no twin qualifies. */
function launcher(lang: string, repoRoot: string): (command: string) => string[] {
  const dir = discoverDir(lang, repoRoot);
  if (dir !== null) return (command) => [join(dir, command)];
  const runner = renderTemplate(language(lang).runner, { version: VERSION }).split(' ');
  if (which(runner[0] ?? '') && qualifies([...runner, 'la-doctor', '--twin'], lang)) return (command) => [...runner, command];
  throw new TwinError(hint('twin.unavailable', lang));
}

export function refuseIfForwarded(lang: string): void {
  if (process.env[FORWARDED_ENV] === '1') throw new TwinError(message('twin.forward-refused', { language: lang }));
}

/** `cmd ARGS`, the `lang` twin's `command`; TwinError when it cannot start. */
function spawnTwin(lang: string, command: string, cmd: string, args: string[], options: SpawnSyncOptions): SpawnSyncReturns<Buffer> {
  const proc = spawnSync(cmd, args, options) as SpawnSyncReturns<Buffer>;
  if (proc.error !== undefined) throw new TwinError(message('twin.launch-failed', { language: lang, command }));
  return proc;
}

/** Run `command` through the `lang` twin with the raw argv; its streams pass through, its exit code returns. */
export function forward(command: string, lang: string, argv: string[], repoRoot: string): number {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot)(command);
  const proc = spawnTwin(lang, command, cmd, [...args, ...argv], { env: env(), stdio: 'inherit' });
  if (proc.signal !== null) return 128 + (osConstants.signals[proc.signal] ?? 0);
  return proc.status ?? 1;
}

/** `command ARGS` in the `lang` twin from the current directory: its exit code (a signal: 2) and stdout; stderr relayed. */
export function runCaptured(command: string, lang: string, args: string[], repoRoot: string): [number, Buffer] {
  refuseIfForwarded(lang);
  const [cmd = '', ...rest] = launcher(lang, repoRoot)(command);
  const proc = spawnTwin(lang, command, cmd, [...rest, ...args], { env: env(), stdio: ['inherit', 'pipe', 'inherit'], maxBuffer: 1 << 30 });
  return [proc.signal !== null || proc.status === null ? 2 : proc.status, proc.stdout];
}

/** The run's stdout as a schema-valid document of `lang` at this version, or null; RelayedFailure on a non-zero exit. */
function documentOf(proc: SpawnSyncReturns<Buffer>, schemaName: string, lang: string): any {
  if (proc.signal === null && proc.status !== null && proc.status > 0) throw new RelayedFailure();
  let document: any = null;
  try {
    document = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(proc.stdout));
  } catch {
    return null;
  }
  if (proc.signal !== null || proc.error !== undefined) return null;
  if (document === null || typeof document !== 'object' || Array.isArray(document)) return null;
  if (validate(schema(schemaName), document).length > 0) return null;
  const identityOk = document.language === lang && document.version === VERSION && document.contract_hash === contractHash();
  return identityOk ? document : null;
}

function factsConsistent(document: any, expectedUnits: string[], topLevel: boolean): boolean {
  if (!topLevel) {
    const units = new Set<string>(document.units.map((u: { unit: string }) => u.unit));
    return expectedUnits.every((unit) => units.has(unit));
  }
  const tops = new Set<string>(document.top_level_units);
  return document.units.length === 0 && document.edges.every((e: { src: string; dst: string }) => tops.has(e.src) && tops.has(e.dst));
}

/** `lang`'s facts from its twin, schema-checked; RelayedFailure when its run fails, TwinError otherwise. */
export function requestFacts(lang: string, repoRoot: string, expectedUnits: string[], topLevel = false): any {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot)('la-arch-check');
  const argv = [...args, '--root', repoRoot, '--language', lang, '--emit', 'facts', ...(topLevel ? ['--top-level'] : [])];
  const proc = spawnTwin(lang, 'la-arch-check', cmd, argv, { env: env(), stdio: ['inherit', 'pipe', 'inherit'], maxBuffer: 1 << 30 });
  const document = documentOf(proc, 'facts', lang);
  if (document === null || !factsConsistent(document, expectedUnits, topLevel)) throw new TwinError(hint('twin.facts-invalid', lang));
  return document;
}

/** `lang`'s conventions facts for `paths` (relative to `cwd`), one per path in order; errors as `requestFacts`. */
export function requestConventionsFacts(lang: string, cwd: string, paths: string[], repoRoot: string): any[] {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot)('la-check-conventions');
  const proc = spawnTwin(lang, 'la-check-conventions', cmd, [...args, '--language', lang, '--emit', 'facts'], {
    cwd,
    env: env(),
    input: JSON.stringify(paths),
    stdio: ['pipe', 'pipe', 'inherit'],
    maxBuffer: 1 << 30,
  });
  const document = documentOf(proc, 'conventions-facts', lang);
  const inOrder = (files: { path: string }[]): boolean => files.length === paths.length && files.every((f, i) => f.path === paths[i]);
  if (document === null || !inOrder(document.files)) throw new TwinError(hint('twin.facts-invalid', lang));
  return document.files;
}

/** `command --language lang ARGS` in the `lang` twin, streams relayed; its exit code (a signal: 2). */
export function runLanguage(command: string, lang: string, args: string[], cwd: string, repoRoot: string): number {
  refuseIfForwarded(lang);
  const [cmd = '', ...rest] = launcher(lang, repoRoot)(command);
  const proc = spawnTwin(lang, command, cmd, [...rest, '--language', lang, ...args], { cwd, env: env(), stdio: 'inherit' });
  return proc.signal !== null || proc.status === null ? 2 : proc.status;
}
