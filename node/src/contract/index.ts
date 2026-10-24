// The shared contract, loaded from the vendored snapshot.
export { fnmatch, globMatch } from './glob.js';
export { pyJson } from './json.js';
export { fullMatch, isPortableRegex } from './regex.js';
export { message, renderTemplate } from './render.js';
export { materializeDefaults, validate } from './schema.js';
export {
  HASH_FILE,
  architecture,
  checkIds,
  computeHash,
  configFile,
  contractHash,
  conventions,
  findings,
  language,
  languageIds,
  languageOf,
  localConfigFile,
  manifest,
  schema,
  schemaNames,
  scriptPath,
  snapshotDir,
} from './snapshot.js';
export { PyFloat, PyTimestamp, canonicalRepr, fixed1, normalize, reprFloat, toPlain } from './values.js';
export { YAMLError, loadYaml } from './yaml.js';
export { WORD, byCodePoint, decodeUtf8, isWordStart, splitLines, splitLinesKeepEnds } from './text.js';
export { which, whichPath } from './which.js';
