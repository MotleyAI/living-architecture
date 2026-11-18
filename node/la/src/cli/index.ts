// The la commands' entry point: their handlers, run through the shared command runner.
import * as config from 'deterministic-refactor/config';
import { type Handler, commandRoot, optional, runCommand } from 'deterministic-refactor/config';
import * as twin from 'deterministic-refactor/twin';
import * as typecheck from 'deterministic-refactor/typecheck';
import * as affected from '../affected/index.js';
import * as archcheck from '../archcheck/index.js';
import * as c4 from '../c4/index.js';
import * as conventions from '../conventions/index.js';
import * as doctor from '../doctor/index.js';
import * as review from '../review/index.js';

const HANDLERS: Record<string, Handler> = {
  'la-config': (args) =>
    args.subcommand === 'show' ? config.runShow(commandRoot(args.root)) : config.runGet(commandRoot(args.root), String(args.key)),
  'la-doctor': (args) => {
    if (args.twin) {
      process.stdout.write(`${twin.identity()}\n`);
      return 0;
    }
    return doctor.run(
      commandRoot(args.root),
      optional(args.plugin),
      Boolean(args.contract_hash),
      Boolean(args.require_config),
      Boolean(args.require_plan_store),
    );
  },
  'la-arch-check': (args) => {
    const emit = optional(args.emit);
    const language = optional(args.language) ?? (emit !== null ? twin.NATIVE_LANGUAGE : null);
    return archcheck.run(commandRoot(args.root), language, emit, Boolean(args.top_level));
  },
  'la-arch-scaffold': (args) => archcheck.runScaffold(commandRoot(args.root)),
  'la-arch-diagrams': (args) => c4.run(commandRoot(args.root)),
  'la-arch-migrate': (args) => c4.runMigrate(commandRoot(args.root)),
  'la-check-conventions': (args) => {
    if (optional(args.emit) !== null) return conventions.emit(optional(args.language) ?? twin.NATIVE_LANGUAGE, process.cwd());
    return conventions.checkConventions({
      repoRoot: config.findRepoRoot(process.cwd()),
      pr: optional(args.pr),
      repo: optional(args.repo),
      base: optional(args.base),
      files: args.files as string[],
      excludes: args.exclude as string[],
      capPct: typeof args.text_ratio_cap === 'number' ? args.text_ratio_cap : null,
    });
  },
  'la-count-comments': (args) => conventions.countComments(args.argv as string[]),
  'la-affected-tests': (args) => {
    const language = optional(args.language);
    return language !== null ? affected.serve(process.cwd(), language) : affected.run(process.cwd(), String(args.base));
  },
  'la-typecheck': (args) =>
    typecheck.run(process.cwd(), Boolean(args.write_baseline), optional(args.language), optional(args.realign_from)),
};

/** The exit code of the la command `command` run with `argv`. */
export function dispatch(command: string, argv: string[]): number {
  return runCommand(command, argv, HANDLERS, review.runShim);
}

/** A bin's entry: run `command` with the process argv and exit with its code once output is flushed. */
export function main(command: string): void {
  process.exitCode = dispatch(command, process.argv.slice(2));
}
