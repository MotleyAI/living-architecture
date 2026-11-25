// `trmv-doctor`: check the installed trmv tools match the plugin's minor series and the config trmv reads is valid.
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  ConfigError,
  bothFilesProblem,
  checkFormat,
  configSource,
  loadWithLanguages,
  repoLanguages,
} from '../config/index.js';
import { TRMV, contractHash, language, message, pluginProblem, which } from '../contract/index.js';
import { NATIVE_LANGUAGE, VERSION } from '../index.js';
import * as twin from '../twin/index.js';

const REQUIRED_EXECUTABLES = ['git'];

const install = (version: string): string => twin.installCommand(NATIVE_LANGUAGE, twin.trmvIdentity(), version);

/** The problems of the config trmv reads, and the executables its repo languages need. */
function configProblems(root: string, requireConfig: boolean): [string[], string[]] {
  const refusal = checkFormat(root);
  if (refusal !== null) return [[refusal], []];
  const problems = requireConfig && configSource(root) === null ? [message('doctor.trmv-config-missing')] : [];
  let settings;
  try {
    settings = loadWithLanguages(root)[1];
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [[...problems, error.message], []];
  }
  if (!existsSync(join(root, '.git'))) return [problems, []];
  let languages: string[];
  try {
    languages = repoLanguages(root, settings);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [[...problems, error.message], []];
  }
  return [problems, languages.flatMap((id) => language(id).executables as string[])];
}

/** Problems found; empty means healthy. Both config files present replace every check that reads the config. */
export function runChecks(root: string, plugin: string | null = null, requireConfig = false): string[] {
  const problems: string[] = [];
  const version = plugin !== null ? pluginProblem(plugin, TRMV.yaml('cli.yaml').plugin, VERSION, install) : null;
  if (version !== null) problems.push(version);
  const executables = [...REQUIRED_EXECUTABLES];
  const both = bothFilesProblem(root);
  if (both !== null) problems.push(both);
  else {
    const [found, needed] = configProblems(root, requireConfig);
    problems.push(...found);
    executables.push(...needed);
  }
  problems.push(...executables.filter((exe) => !which(exe)).map((exe) => message('doctor.missing-executable', { exe })));
  return problems;
}

export function run(root: string, plugin: string | null, printHash: boolean, requireConfig = false): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, plugin, requireConfig);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    const source = configSource(root) ?? message('doctor.no-config-file');
    process.stdout.write(`${message('doctor.ok', { package: TRMV.yaml('cli.yaml').plugin, version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
