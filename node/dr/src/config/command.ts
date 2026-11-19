// Running a command: forward it to its native twin, or parse argv per the shared manifest, check the repo format
// and dispatch to its handler.
import { resolve } from 'node:path';
import { manifest, message } from '../contract/index.js';
import { type Args, HelpRequested, UsageError, parse } from '../contract/parser.js';
import * as twin from '../twin/index.js';
import { bothFilesProblem } from './files.js';
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
function forwarded(command: string, lang: string, argv: string[], who: twin.Identity | undefined): number {
  try {
    return twin.forward(command, lang, argv, findRepoRoot(process.cwd()), who);
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    process.stderr.write(`${message('twin.error', { prog: command, error: error.message })}\n`);
    return 2;
  }
}

/** How a package runs its commands: its manifest, the config file whose format it checks (default: the one dr
 * reads), its twin identity, and the runner of commands the manifest backs with a bundled script. */
export interface CommandSet {
  commands?: Record<string, any>;
  configFile?: string;
  who?: twin.Identity;
  shim?: (command: string, argv: string[]) => number;
}

/**
 * The exit code of `command` run with `argv`: forwarded to its native twin, or parsed, refused when both config files
 * are present or the format is wrong (unless exempt), and dispatched to its handler.
 */
export function runCommand(command: string, argv: string[], handlers: Record<string, Handler>, set: CommandSet = {}): number {
  const spec = (set.commands ?? manifest())[command];
  const native: string[] | undefined = spec.native;
  if (native !== undefined && !native.includes(twin.NATIVE_LANGUAGE)) return forwarded(command, native[0] ?? '', argv, set.who);
  if (spec.script !== undefined && set.shim !== undefined) return set.shim(command, argv);
  let args: Args;
  try {
    args = parse(command, argv, set.commands);
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
    const root = checkedRoot(args);
    const problem = bothFilesProblem(root) ?? checkFormat(root, set.configFile ?? null);
    if (problem !== null) {
      process.stderr.write(`${problem}\n`);
      return 2;
    }
  }
  const handler = handlers[command];
  if (handler === undefined) throw new Error(`no handler for ${command}`);
  return handler(args, argv);
}
