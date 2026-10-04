// `la-arch-scaffold`: a starter model, views and arc42 from the measured top-level units and import edges.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { diagramBlock, parseModel, parseViews, readIndex } from '../c4/index.js';
import { message } from '../contract/index.js';
import { NATIVE_LANGUAGE, requestFacts } from '../twin/index.js';
import { type Facts, nativeTopLevelFacts } from './facts.js';
import { ArchCheckError, INDEX_REL, type Index, declaredLanguages, loadIndex, resolveLayout, resolveTsconfig, section } from './index-file.js';
import { separator } from './nodes.js';
import { compareStrings } from './order.js';

const SPECIFICATION_REL = 'architecture/model/specification.c4';
const VIEWS_REL = 'architecture/views.c4';
const ARC42_REL = 'architecture/system.arc42.md';

const SPECIFICATION = `specification {
  element system
  element node
  element bucket {
    #virtual
  }
  tag legacy
  tag virtual
}
`;

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

function sortedFiles(dir: string, suffix: string): string[] {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) return [];
  return readdirSync(dir)
    .filter((name) => name.endsWith(suffix) && isFile(join(dir, name)))
    .sort(compareStrings);
}

/** The first file the scaffold would clash with, repo-relative; null when the model is still unwritten. */
function existingOutput(root: string): string | null {
  const candidates = [
    ...sortedFiles(join(root, 'architecture', 'model'), '.c4').map((name) => `architecture/model/${name}`),
    VIEWS_REL,
    ...sortedFiles(join(root, 'architecture'), '.arc42.md').map((name) => `architecture/${name}`),
  ];
  return candidates.find((rel) => isFile(join(root, rel))) ?? null;
}

const lastSegment = (unit: string, language: string): string => unit.split(separator(language)).pop() ?? '';

/** The unit's last segment with non-identifier characters as `_`, prefixed `n_` when it starts with a digit. */
export function nodeId(unit: string, language: string): string {
  const ident = lastSegment(unit, language).replace(/[^A-Za-z0-9_]/g, '_');
  return /^[0-9]/.test(ident) ? `n_${ident}` : ident;
}

function ids(facts: Facts): Map<string, string> {
  const out = new Map<string, string>();
  const owners = new Map<string, string>();
  for (const unit of facts.top_level_units) {
    const id = nodeId(unit, facts.language);
    const first = owners.get(id);
    if (first !== undefined) {
      throw new ArchCheckError(message('arch-scaffold.id-collision', { language: facts.language, first, second: unit, id }));
    }
    owners.set(id, unit);
    out.set(unit, id);
  }
  return out;
}

function renderModel(facts: Facts): string {
  const byUnit = ids(facts);
  const lines = ['model {', `  ${facts.language} = system '${facts.language}' {`];
  for (const unit of facts.top_level_units) {
    lines.push(
      `    ${byUnit.get(unit)} = node '${lastSegment(unit, facts.language)}' {`,
      '      metadata {',
      `        package '${unit}'`,
      '      }',
      '    }',
    );
  }
  if (facts.edges.length > 0) {
    lines.push('', ...facts.edges.map((edge) => `    ${byUnit.get(edge.src)} -> ${byUnit.get(edge.dst)}`));
  }
  lines.push('  }', '}');
  return `${lines.join('\n')}\n`;
}

function renderViews(languages: string[]): string {
  const lines = ['views {'];
  for (const language of languages) {
    lines.push(`  view ${language} of ${language} {`, `    title '${language}'`, '    include *', '  }');
  }
  lines.push('}');
  return `${lines.join('\n')}\n`;
}

function indexText(root: string, index: Index, languages: string[]): string {
  let text = readFileSync(join(root, INDEX_REL), 'utf8');
  if (text && !text.endsWith('\n')) text += '\n';
  if (!index.has('legacy_arrows')) text += 'legacy_arrows: {baseline: 0}\n';
  if (!index.has('diagrams')) text += `diagrams:\n  ${ARC42_REL}: [${languages.join(', ')}]\n`;
  return text;
}

/** The arc42 skeleton with each view's diagram, rendered from the scaffold's own model and views. */
function arc42(files: Map<string, string>, languages: string[]): string {
  const staging = mkdtempSync(join(tmpdir(), 'la-arch-scaffold-'));
  try {
    for (const [rel, text] of files) {
      mkdirSync(dirname(join(staging, rel)), { recursive: true });
      writeFileSync(join(staging, rel), text, 'utf8');
    }
    const model = parseModel(staging);
    const views = new Map(parseViews(staging, model).views.map((view) => [view.id, view]));
    const blocks = languages.map((language) => {
      const view = views.get(language);
      if (view === undefined) throw new Error(`no view ${language}`);
      return diagramBlock(view, model);
    });
    return `${message('arch-scaffold.arc42-head')}\n${blocks.join('\n\n')}\n\n${message('arch-scaffold.arc42-tail')}`;
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
}

function languageFacts(root: string, index: Index, language: string): Facts {
  if (language !== NATIVE_LANGUAGE) return requestFacts(language, root, [], true) as Facts;
  const values = section(index, language);
  return nativeTopLevelFacts({ ...resolveLayout(root, values), tsconfig: resolveTsconfig(root, values.tsconfig) }, language);
}

/** Every scaffold output, repo-relative path -> text, in write order; ArchCheckError when one cannot be made. */
export function scaffold(root: string): Map<string, string> {
  const usable = readIndex(root);
  if (typeof usable === 'string') throw new ArchCheckError(usable);
  const index = loadIndex(root);
  const existing = existingOutput(root);
  if (existing !== null) throw new ArchCheckError(message('arch-scaffold.exists', { path: existing }));
  const languages = declaredLanguages(index);
  const files = new Map<string, string>([[SPECIFICATION_REL, SPECIFICATION]]);
  for (const language of languages) files.set(`architecture/model/${language}.c4`, renderModel(languageFacts(root, index, language)));
  files.set(VIEWS_REL, renderViews(languages));
  const newIndex = indexText(root, index, languages);
  files.set(ARC42_REL, arc42(new Map([...files, [INDEX_REL, newIndex]]), languages));
  files.set(INDEX_REL, newIndex);
  return files;
}
