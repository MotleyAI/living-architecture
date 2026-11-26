// The trmv commands' entry point: their handlers, run through the shared command runner.
import * as config from '../config/index.js';
import { type Handler, commandRoot, optional, runCommand } from '../config/index.js';
import * as doctor from '../doctor/index.js';
import * as refactor from '../refactor/index.js';
import * as twin from '../twin/index.js';
import * as typecheck from '../typecheck/index.js';

/** The parsed options with null (not given) as undefined. */
const given = (args: Record<string, unknown>): Record<string, any> =>
  Object.fromEntries(Object.entries(args).map(([key, value]) => [key, value === null ? undefined : value]));

const HANDLERS: Record<string, Handler> = {
  'trmv-config': (args) => {
    const root = commandRoot(args.root);
    return args.subcommand === 'show'
      ? config.runShow('trmv-config', root, config.trmvView)
      : config.runGet('trmv-config', root, String(args.key), config.trmvView);
  },
  'trmv-doctor': (args) => {
    if (args.twin) {
      process.stdout.write(`${twin.identity()}\n`);
      return 0;
    }
    return doctor.run(commandRoot(args.root), optional(args.plugin), Boolean(args.contract_hash), Boolean(args.require_config));
  },
  'trmv-typecheck': (args) =>
    typecheck.run(process.cwd(), Boolean(args.write_baseline), optional(args.language), optional(args.realign_from), optional(args.base)),
  'trmv-refactor': (args, argv) => refactor.runRefactor(argv, given(args) as refactor.RefactorArgs),
  'trmv-compliance': (args) => refactor.runCompliance(args.paths as string[], optional(args.select), args.attr as string[]),
  'trmv-mock-lint': (args) => refactor.runMockLint(args.paths as string[], optional(args.base)),
};

/** The exit code of the trmv command `command` run with `argv`. */
export function dispatch(command: string, argv: string[]): number {
  return runCommand(command, argv, HANDLERS);
}

/** A bin's entry: run `command` with the process argv and exit with its code once output is flushed. */
export function main(command: string): void {
  process.exitCode = dispatch(command, process.argv.slice(2));
}
