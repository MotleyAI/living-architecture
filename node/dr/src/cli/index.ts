// The dr commands' entry point: their handlers, run through the shared command runner.
import { type Handler, optional, runCommand } from '../config/index.js';
import * as refactor from '../refactor/index.js';

/** The parsed options with null (not given) as undefined. */
const given = (args: Record<string, unknown>): Record<string, any> =>
  Object.fromEntries(Object.entries(args).map(([key, value]) => [key, value === null ? undefined : value]));

const HANDLERS: Record<string, Handler> = {
  'dr-refactor': (args, argv) => refactor.runRefactor(argv, given(args) as refactor.RefactorArgs),
  'dr-compliance': (args) => refactor.runCompliance(args.paths as string[], optional(args.select), args.attr as string[]),
  'dr-mock-lint': (args) => refactor.runMockLint(args.paths as string[], optional(args.base)),
};

/** The exit code of the dr command `command` run with `argv`. */
export function dispatch(command: string, argv: string[]): number {
  return runCommand(command, argv, HANDLERS);
}

/** A bin's entry: run `command` with the process argv and exit with its code once output is flushed. */
export function main(command: string): void {
  process.exitCode = dispatch(command, process.argv.slice(2));
}
