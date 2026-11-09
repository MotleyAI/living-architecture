// Reads of `architecture/index.yaml` for diagram settings and migration; problems become messages.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { DuplicateKeyError, YAMLError, decodeUtf8OrNull, loadYaml, message } from '../contract/index.js';

export const INDEX_REL = 'architecture/index.yaml';

/** `architecture/index.yaml` as its exact text and as the mapping it holds. */
export interface Index {
  text: string;
  data: Map<unknown, unknown>;
}

/** The index, a message explaining why it is unusable, or null when it is absent (never throws). */
export function loadIndex(root: string): Index | string | null {
  const path = join(root, INDEX_REL);
  if (!existsSync(path) || !statSync(path).isFile()) return null;
  const text = decodeUtf8OrNull(readFileSync(path));
  if (text === null) return message('c4.index-invalid-yaml');
  let data: unknown;
  try {
    data = loadYaml(text);
  } catch (error) {
    if (error instanceof DuplicateKeyError) return message('c4.index-duplicate-key', { error: error.message });
    if (error instanceof YAMLError) return message('c4.index-invalid-yaml');
    throw error;
  }
  return data instanceof Map ? { text, data } : message('c4.index-not-mapping');
}

/** The parsed index mapping, or a message explaining why it is unusable (never throws). */
export function readIndex(root: string): Map<unknown, unknown> | string {
  const index = loadIndex(root);
  if (index === null) return message('c4.index-missing');
  return typeof index === 'string' ? index : index.data;
}
