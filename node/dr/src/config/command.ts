// Running a command: forward it to its native twin, or parse argv per the shared manifest, check the repo format
// and dispatch to its handler.
import { resolve } from 'node:path';
import { manifest, message } from '../contract/index.js';
import { type Args, HelpRequested, UsageError, parse } from '../contract/parser.js';
import * as twin from '../twin/index.js';
import { checkFormat } from './format.js';
import { findRepoRoot } from './index.js';

export type Handler = (args: Args, argv: string[]) => number;

/** `--root` resolved, else the git root of the cwd. */
export const commandRoot = (value: unknown): string =>
  typeof value === 'string' && value ? resolve(value) : findRepoRoot(process.cwd());

/** A string option, or null when not given. */
export const optional = (value: unknown): string | null => (typeof value === 'string' ? value : null);

/** The repo whose format a command checks: `--root`, else the git root of `--project`, else of the cwd. */
const checkedRoot = (args: Args): string => {
  const project = optional(args.project);
  return optional(args.root) || !project ? commandRoot(args.root) : findRepoRoot(project);
};

/** Run a command another twin implements: forward the raw argv, or exit 2 with the hint. */
function forwarded(command: string, lang: string, argv: string[]): number {
  try {
    return twin.forward(command, lang, argv, findRepoRoot(process.cwd()));
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    process.stderr.write(`${message('twin.error', { prog: command, error: error.message })}\n`);
    return 2;
  }
}

/** The exit code of `command` run with `argv`; `shim` runs a command the manifest backs with a bundled script. */
export function runCommand(
  command: string,
  argv: string[],
  handlers: Record<string, Handler>,
  shim?: (command: string, argv: string[]) => number,
): number {
  const spec = manifest()[command];
  const native: string[] | undefined = spec.native;
  if (native !== undefined && !native.includes(twin.NATIVE_LANGUAGE)) return forwarded(command, native[0] ?? '', argv);
  if (spec.script !== undefined && shim !== undefined) return shim(command, argv);
  let args: Args;
  try {
    args = parse(command, argv);
  } catch (error) {
    if (error instanceof HelpRequested) {
      process.stdout.write(error.text);
      return 0;
    }
    if (!(error instanceof UsageError)) throw error;
    process.stderr.write(`usage: ${command} [-h] ...\n${error.command}: error: ${error.message}\n`);
    return error.exitCode;
  }
  if (spec.format !== 'exempt') {
    const problem = checkFormat(checkedRoot(args));
    if (problem !== null) {
      process.stderr.write(`${problem}\n`);
      return 2;
    }
  }
  const handler = handlers[command];
  if (handler === undefined) throw new Error(`no handler for ${command}`);
  return handler(args, argv);
}
