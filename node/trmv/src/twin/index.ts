// Reaching the other twin: identity handshake, discovery on PATH, runner probe, forwarding, documents and language runs.
import { spawnSync, type SpawnSyncOptions, type SpawnSyncReturns } from 'node:child_process';
import { accessSync, constants, realpathSync, statSync } from 'node:fs';
import { constants as osConstants } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { TRMV, type Snapshot, contractHash, language, message, renderTemplate, validate, which } from '../contract/index.js';
import { NATIVE_LANGUAGE, VERSION } from '../index.js';

export { NATIVE_LANGUAGE };
const FORWARDED_ENV = 'LA_FORWARDED';

/** The other twin cannot serve the request; the message is the hint to print. */
export class TwinError extends Error {}

/** The other twin's facts run failed; its stderr was already passed through. */
export class RelayedFailure extends Error {}

/**
 * A package's twin as the other twin's probe sees it: the package, the doctor answering `--twin`, its version, its
 * contract hashes (its own first), and the contract holding the schemas of the documents it exchanges.
 */
export interface Identity {
  package: string;
  doctor: string;
  version: string;
  hashes: string[];
  contract: Snapshot;
}

/** The `--twin` line `who`'s twin of `lang` prints. */
export const line = (who: Identity, lang: string): string => [lang, who.version, ...who.hashes].join(' ');

/** trmv's twin identity. */
export function trmvIdentity(): Identity {
  const cli = TRMV.yaml('cli.yaml');
  return { package: cli.package, doctor: cli.doctor, version: VERSION, hashes: [contractHash()], contract: TRMV };
}

/** This twin's `--twin` line for `who` (default: trmv). */
export function identity(who: Identity = trmvIdentity()): string {
  return line(who, NATIVE_LANGUAGE);
}

/** The command installing `who`'s twin of `lang` at `version` (default: its own). */
export function installCommand(lang: string, who: Identity, version: string = who.version): string {
  return renderTemplate(language(lang).install[who.package], { version });
}

/** The hint `templateId` from `who`'s registry, else from trmv's. */
function hint(templateId: string, lang: string, who: Identity): string {
  const values = { language: lang, package: who.package, version: who.version, install: installCommand(lang, who) };
  const template = who.contract.findings()[templateId];
  return template === undefined ? message(templateId, values) : renderTemplate(template, values);
}

const env = (): NodeJS.ProcessEnv => ({ ...process.env, [FORWARDED_ENV]: '1' });

/** `argv` (a doctor's `--twin` invocation) reports `who`'s twin of `lang`. */
function qualifies(argv: string[], lang: string, who: Identity): boolean {
  const [cmd = '', ...args] = argv;
  const proc = spawnSync(cmd, args, { env: env(), encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  return proc.error === undefined && proc.status === 0 && proc.stdout.trim() === line(who, lang);
}

function executable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

/** The real path of the running entry point's sibling doctor of `who`; null when it is not a file. */
function ownDoctor(who: Identity): string | null {
  try {
    const doctor = realpathSync(join(dirname(realpathSync(process.argv[1] ?? '')), `${who.doctor}.js`));
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

/** The first directory (each real path once, never our own) whose executable doctor of `who` qualifies. */
function discoverDir(lang: string, repoRoot: string, who: Identity): string | null {
  const own = ownDoctor(who);
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
    const doctor = join(dir, who.doctor);
    if (isOwn(doctor, own)) continue;
    if (executable(doctor) && qualifies([doctor, '--twin'], lang, who)) return dir;
  }
  return null;
}

/** How to run one of `who`'s `lang` twin's commands; TwinError when no twin qualifies. */
function launcher(lang: string, repoRoot: string, who: Identity): (command: string) => string[] {
  const dir = discoverDir(lang, repoRoot, who);
  if (dir !== null) return (command) => [join(dir, command)];
  const runner = renderTemplate(language(lang).runner, { package: who.package, version: who.version }).split(' ');
  if (which(runner[0] ?? '') && qualifies([...runner, who.doctor, '--twin'], lang, who)) return (command) => [...runner, command];
  throw new TwinError(hint('twin.unavailable', lang, who));
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

/** Run `command` through `who`'s (default: trmv's) `lang` twin with the raw argv; streams pass through, its exit code returns. */
export function forward(command: string, lang: string, argv: string[], repoRoot: string, who: Identity = trmvIdentity()): number {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot, who)(command);
  const proc = spawnTwin(lang, command, cmd, [...args, ...argv], { env: env(), stdio: 'inherit' });
  if (proc.signal !== null) return 128 + (osConstants.signals[proc.signal] ?? 0);
  return proc.status ?? 1;
}

/**
 * `command ARGS` in `who`'s (default: trmv's) `lang` twin from the current directory: its exit code (a signal: 2) and
 * stdout; stderr relayed.
 */
export function runCaptured(command: string, lang: string, args: string[], repoRoot: string, who: Identity = trmvIdentity()): [number, Buffer] {
  refuseIfForwarded(lang);
  const [cmd = '', ...rest] = launcher(lang, repoRoot, who)(command);
  const proc = spawnTwin(lang, command, cmd, [...rest, ...args], { env: env(), stdio: ['inherit', 'pipe', 'inherit'], maxBuffer: 1 << 30 });
  return [proc.signal !== null || proc.status === null ? 2 : proc.status, proc.stdout];
}

/** The run's stdout as a document of `who`'s `lang` twin, valid against `who`'s schema, or null; RelayedFailure on a non-zero exit. */
function documentOf(proc: SpawnSyncReturns<Buffer>, schemaName: string, lang: string, who: Identity): any {
  if (proc.signal === null && proc.status !== null && proc.status > 0) throw new RelayedFailure();
  let document: any = null;
  try {
    document = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(proc.stdout));
  } catch {
    return null;
  }
  if (proc.signal !== null || proc.error !== undefined) return null;
  if (document === null || typeof document !== 'object' || Array.isArray(document)) return null;
  if (validate(who.contract.schema(schemaName), document, [who.contract]).length > 0) return null;
  const identityOk = document.language === lang && document.version === who.version && document.contract_hash === who.hashes[0];
  return identityOk ? document : null;
}

/** What `requestDocument` sends and accepts: the working directory, stdin, and a check on the valid document. */
export interface DocumentRequest {
  repoRoot: string;
  cwd?: string;
  stdin?: string;
  accept?: (document: any) => boolean;
}

/**
 * `command ARGS` in `who`'s `lang` twin: its stdout as one document valid against `who`'s schema `schemaName` that
 * `accept` takes; RelayedFailure when the run fails, TwinError otherwise.
 */
export function requestDocument(lang: string, who: Identity, command: string, args: string[], schemaName: string, request: DocumentRequest): any {
  refuseIfForwarded(lang);
  const [cmd = '', ...rest] = launcher(lang, request.repoRoot, who)(command);
  const proc = spawnTwin(lang, command, cmd, [...rest, ...args], {
    cwd: request.cwd,
    env: env(),
    input: request.stdin,
    stdio: [request.stdin === undefined ? 'inherit' : 'pipe', 'pipe', 'inherit'],
    maxBuffer: 1 << 30,
  });
  const document = documentOf(proc, schemaName, lang, who);
  if (document === null || !(request.accept ?? (() => true))(document)) throw new TwinError(hint('twin.facts-invalid', lang, who));
  return document;
}

/** `command --language lang ARGS` in `who`'s (default: trmv's) `lang` twin, streams relayed; its exit code (a signal: 2). */
export function runLanguage(command: string, lang: string, args: string[], cwd: string, repoRoot: string, who: Identity = trmvIdentity()): number {
  refuseIfForwarded(lang);
  const [cmd = '', ...rest] = launcher(lang, repoRoot, who)(command);
  const proc = spawnTwin(lang, command, cmd, [...rest, '--language', lang, ...args], { cwd, env: env(), stdio: 'inherit' });
  return proc.signal !== null || proc.status === null ? 2 : proc.status;
}
