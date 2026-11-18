// `dr-refactor rename-map MAP`: the map file read and checked against the shared schema.
import { existsSync, statSync } from 'node:fs';
import { DuplicateKeyError, YAMLError, decodeUtf8OrNull, isOsError, loadYaml, message, readFile, schema, toPlain, validate } from '../contract/index.js';

/** One entry of a rename map, as written: a located entry's `file`, or a module entry's `module`. */
export interface MapEntry {
  file?: string;
  module?: string;
  symbol?: string;
  line?: number;
  col?: number;
  offset?: number;
  new_name?: string;
  retarget?: string;
}

/** The map cannot be used; the message is user-facing, exit 2. */
export class MapError extends Error {}

function document(path: string): unknown {
  if (!existsSync(path) || !statSync(path).isFile()) return null;
  let bytes: Buffer;
  try {
    bytes = readFile(path);
  } catch (error) {
    if (isOsError(error)) return null;
    throw error;
  }
  const text = decodeUtf8OrNull(bytes);
  if (text === null) return null;
  try {
    return toPlain(loadYaml(text));
  } catch (error) {
    if (error instanceof DuplicateKeyError || error instanceof YAMLError) return null;
    throw error;
  }
}

/** The entries of the map at `path` (`shown` in messages); MapError naming every invalid entry in index order (1-based;
 * entry 1 for a file that holds no list of entries). */
export function loadMap(path: string, shown: string): MapEntry[] {
  const data = document(path);
  const invalid = (indexes: number[]): MapError =>
    new MapError(indexes.map((index) => message('refactor.map-invalid', { map: shown, index })).join('\n'));
  if (!Array.isArray(data) || data.length === 0) throw invalid([1]);
  const bad = data.flatMap((entry, i) => (validate(schema('rename-map'), [entry]).length > 0 ? [i + 1] : []));
  if (bad.length > 0) throw invalid(bad);
  return data as MapEntry[];
}

/** The source file an entry names: its `file`, or a module entry's `module`. */
export const entrySource = (entry: MapEntry): string => entry.file ?? entry.module ?? '';
