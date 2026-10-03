// Lenient reads of `architecture/index.yaml` for diagram settings; problems become findings.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { YAMLError, loadYaml, message } from '../contract/index.js';

/** The parsed index mapping, or a message explaining why it is unusable (never throws). */
export function readIndex(root: string): Map<unknown, unknown> | string {
  const path = join(root, 'architecture', 'index.yaml');
  if (!existsSync(path) || !statSync(path).isFile()) return message('c4.index-missing');
  let index: unknown;
  try {
    index = loadYaml(readFileSync(path, 'utf8'));
  } catch (error) {
    if (error instanceof YAMLError) return message('c4.index-invalid-yaml');
    throw error;
  }
  return index instanceof Map ? index : message('c4.index-not-mapping');
}
