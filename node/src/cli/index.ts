// Every command's entry point: parse argv per the shared manifest, dispatch to the owning node's handler.
import { resolve } from 'node:path';
import * as archcheck from '../archcheck/index.js';
import * as c4 from '../c4/index.js';
import * as config from '../config/index.js';
import { manifest, message } from '../contract/index.js';
import * as doctor from '../doctor/index.js';
import * as review from '../review/index.js';
import * as twin from '../twin/index.js';
import { type Args, HelpRequested, UsageError, help, parse } from './parser.js';

const root = (value: unknown): string =>
  typeof value === 'string' && value ? resolve(value) : config.findRepoRoot(process.cwd());

const optional = (value: unknown): string | null => (typeof value === 'string' ? value : null);

const HANDLERS: Record<string, (args: Args) => number> = {
  'la-config': (args) =>
    args.subcommand === 'show' ? config.runShow(root(args.root)) : config.runGet(root(args.root), String(args.key)),
  'la-doctor': (args) => {
    if (args.twin) {
      process.stdout.write(`${twin.identity()}\n`);
      return 0;
    }
    return doctor.run(root(args.root), optional(args.expect), Boolean(args.contract_hash));
  },
  'la-arch-check': (args) => {
    const emit = optional(args.emit);
    const language = optional(args.language) ?? (emit !== null ? twin.NATIVE_LANGUAGE : null);
    return archcheck.run(root(args.root), language, emit);
  },
  'la-arch-diagrams': (args) => c4.run(root(args.root)),
};

/** Run a command another twin implements: forward the raw argv, or exit 2 with the hint. */
function forwarded(command: string, lang: string, argv: string[]): number {
  try {
    return twin.forward(command, lang, argv, config.findRepoRoot(process.cwd()));
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    process.stderr.write(`${message('twin.error', { prog: command, error: error.message })}\n`);
    return 2;
  }
}

/** The exit code of `command` run with `argv`. */
export function dispatch(command: string, argv: string[]): number {
  const spec = manifest()[command];
  const native: string[] | undefined = spec.native;
  if (native !== undefined && !native.includes(twin.NATIVE_LANGUAGE)) return forwarded(command, native[0] ?? '', argv);
  if (spec.script !== undefined) return review.runShim(command, argv);
  let args: Args;
  try {
    args = parse(command, argv);
  } catch (error) {
    if (error instanceof HelpRequested) {
      process.stdout.write(help(command));
      return 0;
    }
    if (!(error instanceof UsageError)) throw error;
    process.stderr.write(`usage: ${command} [-h] ...\n${error.command}: error: ${error.message}\n`);
    return error.exitCode;
  }
  const handler = HANDLERS[command];
  if (handler === undefined) throw new Error(`no handler for ${command}`);
  return handler(args);
}

/** A bin's entry: run `command` with the process argv and exit with its code once output is flushed. */
export function main(command: string): void {
  process.exitCode = dispatch(command, process.argv.slice(2));
}
