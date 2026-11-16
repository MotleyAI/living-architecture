// `dr-refactor rename-map MAP`: the map file read and checked against the shared schema.
import { existsSync, statSync } from 'node:fs';
import { DuplicateKeyError, YAMLError, decodeUtf8OrNull, isOsError, loadYaml, message, readFile, schema, toPlain, validate } from '../contract/index.js';

/** One entry of a rename map, as written. */
export interface MapEntry {
  file: string;
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

/** The entries of the map at `path` (`shown` in messages); MapError naming the first invalid entry (1-based; entry 1
 * for a file that holds no list of entries). */
export function loadMap(path: string, shown: string): MapEntry[] {
  const data = document(path);
  const invalid = (index: number): MapError => new MapError(message('refactor.map-invalid', { map: shown, index }));
  if (!Array.isArray(data) || data.length === 0) throw invalid(1);
  const bad = data.findIndex((entry) => validate(schema('rename-map'), [entry]).length > 0);
  if (bad >= 0) throw invalid(bad + 1);
  return data as MapEntry[];
}
