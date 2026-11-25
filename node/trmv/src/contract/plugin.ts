// A doctor's `--plugin DIR`: the calling plugin's version against the installed tools' minor series.
import { statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { readFile } from './os-error.js';
import { message } from './render.js';

const PLUGIN_MANIFEST = join('.claude-plugin', 'plugin.json');
const VERSION_FORM = /^(\d+)\.(\d+)\..+$/s;

/** A missing entry or a path under a regular file is absent; other stat errors propagate. */
function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT' || code === 'ENOTDIR') return false;
    throw error;
  }
}

/** Major and minor of `<digits>.<digits>.<rest>` as written, or null. */
function series(version: string): [string, string] | null {
  const match = VERSION_FORM.exec(version);
  return match === null ? null : [match[1] ?? '', match[2] ?? ''];
}

const canonical = (parts: [string, string]): string => parts.map((part) => part.replace(/^0+/, '') || '0').join('.');

/** The installed tools a doctor checks: their package's short name, version and install command at a version. */
interface Tools {
  name: string;
  version: string;
  install: (version: string) => string;
}

function versionProblem(tools: Tools, expected: string, plugin: [string, string]): string | null {
  const installed = series(tools.version);
  if (installed !== null && canonical(installed) === canonical(plugin)) return null;
  return message('doctor.version-mismatch', {
    package: tools.name,
    installed: tools.version,
    expected,
    series: plugin.join('.'),
    install: tools.install(expected),
  });
}

function manifestProblem(manifest: string, raw: Buffer, tools: Tools): string | null {
  let version: unknown = null;
  try {
    const data: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw));
    if (data !== null && typeof data === 'object' && !Array.isArray(data)) version = (data as Record<string, unknown>).version;
  } catch {
    version = null;
  }
  const parts = typeof version === 'string' && !/\p{Surrogate}/u.test(version) ? series(version) : null;
  if (typeof version !== 'string' || parts === null) return message('doctor.plugin-invalid', { path: manifest });
  return versionProblem(tools, version, parts);
}

/**
 * The tools `name` at `version` against the nearest `.claude-plugin/plugin.json` at or above `plugin`, or null when
 * they share its minor series; `install(v)` is the command installing the tools at `v`.
 */
export function pluginProblem(plugin: string, name: string, version: string, install: (v: string) => string): string | null {
  const tools: Tools = { name, version, install };
  const start = resolve(plugin);
  for (let dir = start; ; dir = dirname(dir)) {
    const manifest = join(dir, PLUGIN_MANIFEST);
    let raw: Buffer | null;
    try {
      raw = isFile(manifest) ? readFile(manifest) : null;
    } catch {
      return message('doctor.plugin-unreadable', { path: manifest });
    }
    if (raw !== null) return manifestProblem(manifest, raw, tools);
    if (dirname(dir) === dir) return message('doctor.plugin-not-found', { dir: start });
  }
}
