// Reaching the other twin: identity handshake, discovery on PATH, runner probe, forwarding and facts transport.
import { spawnSync } from 'node:child_process';
import { accessSync, constants, realpathSync, statSync } from 'node:fs';
import { constants as osConstants } from 'node:os';
import { delimiter, join } from 'node:path';
import { contractHash, language, message, renderTemplate, schema, validate } from '../contract/index.js';
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

const onPath = (name: string): boolean =>
  (process.env.PATH ?? '').split(delimiter).some((dir) => dir !== '' && executable(join(dir, name)));

/** The first directory (each real path once) whose executable `la-doctor` qualifies. */
function discoverDir(lang: string, repoRoot: string): string | null {
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
    if (executable(doctor) && qualifies([doctor, '--twin'], lang)) return dir;
  }
  return null;
}

/** How to run one of the `lang` twin's commands; TwinError when no twin qualifies. */
function launcher(lang: string, repoRoot: string): (command: string) => string[] {
  const dir = discoverDir(lang, repoRoot);
  if (dir !== null) return (command) => [join(dir, command)];
  const runner = renderTemplate(language(lang).runner, { version: VERSION }).split(' ');
  if (onPath(runner[0] ?? '') && qualifies([...runner, 'la-doctor', '--twin'], lang)) return (command) => [...runner, command];
  throw new TwinError(hint('twin.unavailable', lang));
}

export function refuseIfForwarded(lang: string): void {
  if (process.env[FORWARDED_ENV] === '1') throw new TwinError(message('twin.forward-refused', { language: lang }));
}

/** Run `command` through the `lang` twin with the raw argv; its streams pass through, its exit code returns. */
export function forward(command: string, lang: string, argv: string[], repoRoot: string): number {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot)(command);
  const proc = spawnSync(cmd, [...args, ...argv], { env: env(), stdio: 'inherit' });
  if (proc.signal !== null) return 128 + (osConstants.signals[proc.signal] ?? 0);
  return proc.status ?? 1;
}

function validFacts(document: any, lang: string, expectedUnits: string[]): boolean {
  if (document === null || typeof document !== 'object' || Array.isArray(document)) return false;
  if (validate(schema('facts'), document).length > 0) return false;
  if (document.language !== lang || document.version !== VERSION || document.contract_hash !== contractHash()) return false;
  const units = new Set<string>(document.units.map((u: { unit: string }) => u.unit));
  return expectedUnits.every((unit) => units.has(unit));
}

/** `lang`'s facts from its twin, schema-checked; RelayedFailure when its run fails, TwinError otherwise. */
export function requestFacts(lang: string, repoRoot: string, expectedUnits: string[]): any {
  refuseIfForwarded(lang);
  const [cmd = '', ...args] = launcher(lang, repoRoot)('la-arch-check');
  const proc = spawnSync(cmd, [...args, '--root', repoRoot, '--language', lang, '--emit', 'facts'], {
    env: env(),
    stdio: ['inherit', 'pipe', 'inherit'],
    maxBuffer: 1 << 30,
  });
  if (proc.signal === null && proc.status !== null && proc.status > 0) throw new RelayedFailure();
  let document: unknown = null;
  try {
    document = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(proc.stdout));
  } catch {
    document = null;
  }
  if (proc.signal !== null || proc.error !== undefined || !validFacts(document, lang, expectedUnits)) {
    throw new TwinError(hint('twin.facts-invalid', lang));
  }
  return document;
}
