// Parsers built from the shared CLI manifest, with argparse's semantics: no abbreviations, `--` ends options,
// a usage error exits 2, a passthrough command hands its raw argv to its handler.
import { manifest } from '../contract/index.js';

export class UsageError extends Error {
  readonly exitCode = 2;

  constructor(
    readonly command: string,
    message: string,
  ) {
    super(message);
  }
}

/** `--help` was asked for; the text goes to stdout and the command exits 0. */
export class HelpRequested extends Error {
  constructor(readonly text: string) {
    super(text);
  }
}

interface OptionSpec {
  name: string;
  type: 'string' | 'path' | 'int' | 'float' | 'flag';
  help: string;
  dest?: string;
  metavar?: string;
  choices?: string[];
  default?: unknown;
  required?: boolean;
  repeatable?: boolean;
  store?: boolean;
  internal?: boolean;
}

interface PositionalSpec {
  name: string;
  help: string;
  nargs?: '?' | '*' | '+';
}

interface CommandSpec {
  help: string;
  options?: OptionSpec[];
  positionals?: PositionalSpec[];
  subcommands?: Record<string, CommandSpec>;
  require_one_of?: string[];
  passthrough?: boolean;
  usage?: string;
}

export type Args = Record<string, unknown>;

const dest = (option: OptionSpec): string => option.dest ?? option.name.replace(/^-+/, '').replaceAll('-', '_');
const NEGATIVE_NUMBER = /^-\d+$|^-\d*\.\d+$/;
const INT_RE = /^\s*[-+]?\d+(?:_\d+)*\s*$/;
const FLOAT_RE = /^\s*[-+]?(?:(?:\d+(?:_\d+)*)?\.?\d+(?:_\d+)*(?:[eE][-+]?\d+(?:_\d+)*)?|\d+(?:_\d+)*\.|inf|infinity|nan)\s*$/i;

function spec(command: string): CommandSpec {
  const found = manifest()[command] as CommandSpec | undefined;
  if (found === undefined) throw new Error(`unknown command ${command}`);
  return found;
}

function isOption(token: string): boolean {
  return token.startsWith('-') && token !== '-' && !NEGATIVE_NUMBER.test(token);
}

function convert(prog: string, option: OptionSpec, raw: string): unknown {
  let value: unknown = raw;
  if (option.type === 'int') {
    if (!INT_RE.test(raw)) throw new UsageError(prog, `argument ${option.name}: invalid int value: '${raw}'`);
    value = Number(raw.replaceAll('_', ''));
  } else if (option.type === 'float') {
    if (!FLOAT_RE.test(raw)) throw new UsageError(prog, `argument ${option.name}: invalid float value: '${raw}'`);
    value = Number(raw.replaceAll('_', '').trim().replace(/^([-+]?)inf(inity)?$/i, '$1Infinity'));
  }
  if (option.choices !== undefined && !option.choices.includes(String(value))) {
    throw new UsageError(prog, `argument ${option.name}: invalid choice: '${raw}'`);
  }
  return value;
}

function defaults(cmd: CommandSpec): Args {
  const out: Args = {};
  for (const positional of cmd.positionals ?? []) out[positional.name] = positional.nargs === '*' ? [] : null;
  for (const option of cmd.options ?? []) {
    if (option.type === 'flag') out[dest(option)] = option.store === false;
    else if (option.repeatable) out[dest(option)] = [];
    else out[dest(option)] = option.default ?? null;
  }
  return out;
}

/** Assign `values` (in order) to the positionals; a count no nargs accepts is a usage error. */
function assignPositionals(prog: string, cmd: CommandSpec, values: string[], args: Args): void {
  const positionals = cmd.positionals ?? [];
  const minimum = positionals.reduce((n, p) => n + (p.nargs === undefined || p.nargs === '+' ? 1 : 0), 0);
  if (values.length < minimum) {
    const missing = positionals.filter((p) => p.nargs === undefined || p.nargs === '+').map((p) => p.name);
    throw new UsageError(prog, `the following arguments are required: ${missing.join(', ')}`);
  }
  let rest = [...values];
  positionals.forEach((positional, i) => {
    const after = positionals.slice(i + 1).reduce((n, p) => n + (p.nargs === undefined || p.nargs === '+' ? 1 : 0), 0);
    if (positional.nargs === undefined) args[positional.name] = rest.shift();
    else if (positional.nargs === '?') args[positional.name] = rest.length > after ? rest.shift() : null;
    else {
      const take = rest.length - after;
      args[positional.name] = rest.slice(0, take);
      rest = rest.slice(take);
    }
  });
  if (rest.length > 0) throw new UsageError(prog, `unrecognized arguments: ${rest.join(' ')}`);
}

function parseLevel(prog: string, cmd: CommandSpec, argv: string[], args: Args): void {
  const options = new Map((cmd.options ?? []).map((o) => [o.name, o]));
  const subcommands = cmd.subcommands ?? {};
  const positionals: string[] = [];
  const seen = new Set<string>();
  let i = 0;
  let ended = false;
  while (i < argv.length) {
    const token = argv[i] ?? '';
    i += 1;
    if (!ended && token === '--') {
      ended = true;
      continue;
    }
    if (ended || !isOption(token)) {
      if (Object.keys(subcommands).length > 0 && positionals.length === 0) {
        const sub = Object.hasOwn(subcommands, token) ? subcommands[token] : undefined;
        if (sub === undefined) throw new UsageError(prog, `argument subcommand: invalid choice: '${token}'`);
        args.subcommand = token;
        Object.assign(args, defaults(sub));
        parseLevel(`${prog} ${token}`, sub, ended ? ['--', ...argv.slice(i)] : argv.slice(i), args);
        checkRequired(prog, cmd, seen);
        return;
      }
      positionals.push(token);
      continue;
    }
    if (token === '-h' || token === '--help') throw new HelpRequested(renderHelp(prog, cmd));
    const eq = token.indexOf('=');
    const name = eq >= 0 ? token.slice(0, eq) : token;
    const option = options.get(name);
    if (option === undefined) throw new UsageError(prog, `unrecognized arguments: ${token}`);
    seen.add(option.name);
    if (option.type === 'flag') {
      if (eq >= 0) throw new UsageError(prog, `argument ${name}: ignored explicit argument '${token.slice(eq + 1)}'`);
      args[dest(option)] = option.store !== false;
      continue;
    }
    let raw: string;
    if (eq >= 0) raw = token.slice(eq + 1);
    else {
      const next = argv[i];
      if (next === undefined || (isOption(next) && next !== '--') || next === '--') {
        throw new UsageError(prog, `argument ${name}: expected one argument`);
      }
      raw = next;
      i += 1;
    }
    const value = convert(prog, option, raw);
    if (option.repeatable) (args[dest(option)] as unknown[]).push(value);
    else args[dest(option)] = value;
  }
  if (Object.keys(subcommands).length > 0) throw new UsageError(prog, 'the following arguments are required: subcommand');
  assignPositionals(prog, cmd, positionals, args);
  checkRequired(prog, cmd, seen);
}

function checkRequired(prog: string, cmd: CommandSpec, seen: Set<string>): void {
  const missing = (cmd.options ?? []).filter((o) => o.required && !seen.has(o.name)).map((o) => o.name);
  if (missing.length > 0) throw new UsageError(prog, `the following arguments are required: ${missing.join(', ')}`);
}

function truthy(value: unknown): boolean {
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

/** Parse `argv` for `command`: dests (and `subcommand`), or `{argv}` for a passthrough command. */
export function parse(command: string, argv: string[]): Args {
  const cmd = spec(command);
  if (cmd.passthrough) return { argv: [...argv] };
  const args = defaults(cmd);
  parseLevel(command, cmd, argv, args);
  const required = cmd.require_one_of;
  if (required !== undefined && !required.some((d) => truthy(args[d]))) {
    throw new UsageError(command, `one of ${required.join(', ')} is required`);
  }
  return args;
}

function optionLines(cmd: CommandSpec): string[] {
  return (cmd.options ?? [])
    .filter((o) => !o.internal)
    .map((o) => `  ${o.name}${o.type === 'flag' ? '' : ` ${o.metavar ?? dest(o).toUpperCase()}`}  ${o.help}`);
}

/** The command's --help text (internal options omitted). */
export function help(command: string): string {
  return renderHelp(command, spec(command));
}

/** Help for `cmd`, the command or subcommand invoked as `prog`. */
function renderHelp(prog: string, cmd: CommandSpec): string {
  const lines = [`usage: ${cmd.usage?.trimEnd() ?? prog}`, '', cmd.help];
  const positionals = cmd.positionals ?? [];
  if (positionals.length > 0) lines.push('', 'positional arguments:', ...positionals.map((p) => `  ${p.name}  ${p.help}`));
  const subcommands = Object.entries(cmd.subcommands ?? {});
  if (subcommands.length > 0) lines.push('', 'subcommands:', ...subcommands.map(([n, s]) => `  ${n}  ${s.help}`));
  lines.push('', 'options:', '  -h, --help  show this help message and exit', ...optionLines(cmd));
  return `${lines.join('\n')}\n`;
}
