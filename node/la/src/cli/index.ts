// The la commands' entry point: their handlers, run through the shared command runner.
import { spawnSync } from 'node:child_process';
import { constants as osConstants } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import * as drConfig from 'deterministic-refactor/config';
import { type Handler, commandRoot, optional } from 'deterministic-refactor/config';
import * as twin from 'deterministic-refactor/twin';
import * as affected from '../affected/index.js';
import * as archcheck from '../archcheck/index.js';
import * as c4 from '../c4/index.js';
import { laView, runCommand } from '../config/index.js';
import { HelpRequested, UsageError, identity, manifest, message, parse } from '../contract/index.js';
import * as conventions from '../conventions/index.js';
import * as doctor from '../doctor/index.js';
import * as review from '../review/index.js';

const HANDLERS: Record<string, Handler> = {
  'la-config': (args) => {
    const root = commandRoot(args.root);
    return args.subcommand === 'show' ? drConfig.runShow('la-config', root, laView) : drConfig.runGet('la-config', root, String(args.key), laView);
  },
  'la-doctor': (args) => {
    if (args.twin) {
      process.stdout.write(`${twin.identity(identity())}\n`);
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
      repoRoot: drConfig.findRepoRoot(process.cwd()),
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
};

/** The deprecated alias: `dr-typecheck` with the same arguments, after one deprecation line on stderr. */
function laTypecheck(argv: string[]): number {
  try {
    parse('la-typecheck', argv, manifest());
  } catch (error) {
    if (error instanceof HelpRequested) {
      process.stdout.write(error.text);
      return 0;
    }
    if (!(error instanceof UsageError)) throw error;
    process.stderr.write(`usage: la-typecheck [-h] ...\n${error.command}: error: ${error.message}\n`);
    return error.exitCode;
  }
  if (process.env.LA_FORWARDED !== '1') process.stderr.write(`${message('typecheck-alias.deprecated')}\n`);
  const drTypecheck = join(dirname(resolve(process.argv[1] ?? '')), 'dr-typecheck');
  const proc = spawnSync(drTypecheck, argv, { stdio: 'inherit' });
  if (proc.error !== undefined) throw proc.error;
  return proc.signal !== null ? 128 + (osConstants.signals[proc.signal] ?? 0) : (proc.status ?? 1);
}

/** The exit code of the la command `command` run with `argv`. */
export function dispatch(command: string, argv: string[]): number {
  return command === 'la-typecheck' ? laTypecheck(argv) : runCommand(command, argv, HANDLERS, review.runShim);
}

/** A bin's entry: run `command` with the process argv and exit with its code once output is flushed. */
export function main(command: string): void {
  process.exitCode = dispatch(command, process.argv.slice(2));
}
