// Reading a config file: OS, decode and YAML errors become config errors from the shared templates.
import { isAbsolute, join } from 'node:path';
import {
  DuplicateKeyError,
  YAMLError,
  decodeUtf8OrNull,
  isOsError,
  isRegularFile,
  loadYaml,
  message,
  osErrorText,
  readFile,
} from '../contract/index.js';
import { ConfigError } from './error.js';

/** The text of config file `name`, null when it does not exist; ConfigError when it cannot be read. */
export function readConfigText(root: string, name: string): string | null {
  const path = isAbsolute(name) ? name : join(root, name);
  let bytes: Buffer;
  try {
    if (!isRegularFile(path)) return null;
    bytes = readFile(path);
  } catch (error) {
    if (isOsError(error)) throw new ConfigError(osErrorText(error, root, path));
    throw error;
  }
  const text = decodeUtf8OrNull(bytes);
  if (text === null) throw new ConfigError(message('yaml.invalid', { path: name }));
  return text;
}

/** `text` of config file `name` in the shared YAML profile; ConfigError when it is not valid YAML. */
export function parseConfig(text: string, name: string): unknown {
  try {
    return loadYaml(text);
  } catch (error) {
    if (error instanceof DuplicateKeyError) {
      throw new ConfigError(message('yaml.invalid-because', { path: name, error: error.message }));
    }
    if (error instanceof YAMLError) throw new ConfigError(message('yaml.invalid', { path: name }));
    throw error;
  }
}
