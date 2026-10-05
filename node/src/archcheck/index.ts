// Living-architecture cross-walk checker: code, LikeC4 model, arc42 docs and specs agree.
import { type ModelParse, checkDiagramsFresh, parseModel, parseViews } from '../c4/index.js';
import { ConfigError, loadConfig } from '../config/index.js';
import { message } from '../contract/index.js';
import { LangError } from '../lang/index.js';
import { NATIVE_LANGUAGE, RelayedFailure, TwinError, requestFacts } from '../twin/index.js';
import { checkClaims } from './claims.js';
import { checkArc42, checkLegacyRatchet, checkSpecMapping } from './docs.js';
import { type Facts, nativeFacts, nativeTopLevelFacts } from './facts.js';
import { ArchCheckError, type Index, declaredLanguages, loadIndex, resolveLayout, resolveTsconfig, section } from './index-file.js';
import { type NodeMap, buildNodeMap } from './nodes.js';
import { scaffold, writeScaffold } from './scaffold.js';
import { checkEnforcedTags } from './tags.js';
import { type Witnesses, checkModelTruth } from './truth.js';

export { ArchCheckError } from './index-file.js';

/** What every check reads: the index, its languages, the model and the node map. */
interface Setup {
  index: Index;
  languages: string[];
  model: ModelParse;
  nodeMap: NodeMap;
}

function setup(root: string): Setup {
  const index = loadIndex(root);
  const languages = declaredLanguages(index);
  const model = parseModel(root);
  return { index, languages, model, nodeMap: buildNodeMap(model, languages) };
}

/** Native facts in-process; another language's from its twin. */
function facts(root: string, s: Setup, language: string): Facts {
  if (language === NATIVE_LANGUAGE) {
    const values = section(s.index, language);
    const layout = resolveLayout(root, values);
    return nativeFacts({ ...layout, tsconfig: resolveTsconfig(root, values.tsconfig) }, s.nodeMap, language);
  }
  return requestFacts(language, root, s.nodeMap.units(language)) as Facts;
}

function findings(root: string): string[] {
  const s = setup(root);
  const all = s.languages.map((language) => facts(root, s, language));
  const views = parseViews(root, s.model);
  const witnesses: Witnesses = new Map();
  for (const languageFacts of all) {
    for (const edge of languageFacts.edges) {
      const key = `${edge.src}\0${edge.dst}`;
      if (!witnesses.has(key)) witnesses.set(key, [edge.src_module, edge.dst_module]);
    }
  }
  const arrows: [string, string][] = s.model.relations.map((r) => [r.src, r.dst]);
  const legacyCount = s.model.relations.filter((r) => r.legacy).length;
  const out: string[] = [];
  for (const languageFacts of all) out.push(...checkClaims(s.nodeMap, languageFacts));
  out.push(
    ...checkArc42(root, s.index, s.nodeMap),
    ...checkSpecMapping(root, s.index, s.nodeMap),
    ...checkLegacyRatchet(s.index, legacyCount),
    ...checkModelTruth(witnesses, arrows),
    ...checkEnforcedTags(root, loadConfig(root).issue_key_pattern, s.languages),
    ...checkDiagramsFresh(root, s.model, views),
  );
  return out;
}

/** The native language's facts document (`topLevel`: edges between top-level units, no model). */
export function emitFacts(root: string, language: string, topLevel = false): Facts {
  if (language !== NATIVE_LANGUAGE) throw new ArchCheckError(message('twin.not-native', { language }));
  if (topLevel) {
    const index = loadIndex(root);
    if (!declaredLanguages(index).includes(language)) throw new ArchCheckError(message('arch-check.no-language-section'));
    const values = section(index, language);
    return nativeTopLevelFacts({ ...resolveLayout(root, values), tsconfig: resolveTsconfig(root, values.tsconfig) }, language);
  }
  const s = setup(root);
  if (!s.languages.includes(language)) throw new ArchCheckError(message('arch-check.no-language-section'));
  return facts(root, s, language);
}

/** The text a setup error prints after `arch_check: `, or null when `error` is not a setup error. */
function setupErrorText(error: unknown): string | null {
  if (error instanceof ArchCheckError || error instanceof ConfigError || error instanceof TwinError) return error.message;
  if (error instanceof LangError) return error.message;
  const code = (error as NodeJS.ErrnoException)?.code;
  if (typeof code === 'string' && code.startsWith('E')) return (error as Error).message;
  return null;
}

/** `la-arch-check`: print the findings and a summary, or (`--emit facts`) one language's facts. */
export function run(root: string, language: string | null, emit: string | null, topLevel = false): number {
  let out: string[];
  try {
    if (emit === 'facts' && language !== null) {
      process.stdout.write(`${JSON.stringify(emitFacts(root, language, topLevel), null, 2)}\n`);
      return 0;
    }
    out = findings(root);
  } catch (error) {
    if (error instanceof RelayedFailure) return 2;
    const text = setupErrorText(error);
    if (text === null) throw error;
    process.stderr.write(`${message('arch-check.setup-error', { error: text })}\n`);
    return 2;
  }
  for (const finding of out) process.stdout.write(`${finding}\n`);
  if (out.length > 0) {
    process.stdout.write(`${message('arch-check.summary', { count: out.length })}\n`);
    return 1;
  }
  process.stdout.write(`${message('arch-check.ok')}\n`);
  return 0;
}

/** `la-arch-scaffold`: write the outputs and print each path, or exit 2 having written nothing. */
export function runScaffold(root: string): number {
  let files: Map<string, string>;
  try {
    files = scaffold(root);
    writeScaffold(root, files);
  } catch (error) {
    if (error instanceof RelayedFailure) return 2;
    const text = setupErrorText(error);
    if (text === null) throw error;
    process.stderr.write(`${message('arch-scaffold.error', { error: text })}\n`);
    return 2;
  }
  for (const rel of files.keys()) process.stdout.write(`${message('arch-scaffold.written', { path: rel })}\n`);
  return 0;
}
