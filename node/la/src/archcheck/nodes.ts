// The canonical element map: every model element, with node mappings from metadata and nested units by convention.
import { type Element, type ModelParse, RETIRED_ARC42_KEY } from '../c4/index.js';
import { language, message, schema, validate } from '../contract/index.js';
import { ArchCheckError } from './index-file.js';

/**
 * One model element: a language root (`node` null), a node (`node === id`), or nested under `node`.
 * A node's `units` are its declared units in metadata order; `unit` is a nested element's convention unit.
 */
export interface MapElement {
  id: string;
  language: string;
  node: string | null;
  specs: string[];
  virtual: boolean;
  package: string | null;
  units: string[];
  unit: string | null;
  hasElements: boolean;
}

export const isNode = (element: MapElement): boolean => element.node === element.id;

export class NodeMap {
  constructor(readonly elements: MapElement[]) {}

  elementIds(): Set<string> {
    return new Set(this.elements.map((e) => e.id));
  }

  languageNodes(lang: string): MapElement[] {
    return this.elements.filter((e) => isNode(e) && e.language === lang);
  }

  /** `lang`'s nested elements that map to a unit, in model order. */
  languageDerived(lang: string): MapElement[] {
    return this.elements.filter((e) => e.unit !== null && e.language === lang);
  }

  /** Every declared, then derived unit of `lang`, in model order, each once. */
  units(lang: string): string[] {
    const all = [...this.languageNodes(lang).flatMap((n) => n.units), ...this.languageDerived(lang).map((d) => String(d.unit))];
    return [...new Set(all)];
  }
}

export function separator(lang: string): string {
  return language(lang).unit_separator;
}

function variety(element: Element, roots: Set<string>): string {
  if (element.parent !== null && roots.has(element.parent)) return element.virtual ? 'virtual' : 'precise';
  return 'element';
}

/** The retired-key error first, then the schema errors of the other keys. */
function metadataErrors(element: Element, roots: Set<string>): string[] {
  const errors: string[] = [];
  if (Object.hasOwn(element.metadata, RETIRED_ARC42_KEY)) errors.push(message('arch-check.arc42-key-retired', { element: element.id }));
  const rest = Object.fromEntries(Object.entries(element.metadata).filter(([key]) => key !== RETIRED_ARC42_KEY));
  const found = validate({ ...schema('node'), $ref: `#/$defs/${variety(element, roots)}` }, rest);
  return [...errors, ...found.map((error) => message('arch-check.metadata-invalid', { element: element.id, error }))];
}

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.map(String) : []);

function problems(model: ModelParse, languages: string[]): string[] {
  const out: string[] = [];
  const roots = new Set(model.elements.filter((e) => e.parent === null).map((e) => e.id));
  for (const element of model.elements) {
    if (element.parent === null && !languages.includes(element.id)) {
      out.push(message('arch-check.root-undeclared', { element: element.id }));
    } else if (element.metadataProblems.length > 0) out.push(...element.metadataProblems);
    else out.push(...metadataErrors(element, roots));
  }
  for (const lang of languages) if (!roots.has(lang)) out.push(message('arch-check.root-missing', { language: lang }));
  return out;
}

function entry(id: string, lang: string, node: string | null, specs: string[]): MapElement {
  return { id, language: lang, node, specs, virtual: false, package: null, units: [], unit: null, hasElements: false };
}

function toNode(element: Element, lang: string): MapElement {
  const meta = element.metadata;
  const pkg = meta.package;
  const units = element.virtual ? strings(meta.packages) : [String(pkg), ...strings(meta.claims)];
  return {
    ...entry(element.id, lang, element.id, strings(meta.specs)),
    virtual: element.virtual,
    package: typeof pkg === 'string' ? pkg : null,
    units,
  };
}

/** The map for `model`; ArchCheckError naming every root and metadata problem, in model order. */
export function buildNodeMap(model: ModelParse, languages: string[]): NodeMap {
  const found = problems(model, languages);
  if (found.length > 0) throw new ArchCheckError(found.join('; '));
  const roots = new Set(model.elements.filter((e) => e.parent === null).map((e) => e.id));
  const byId = new Map<string, MapElement>();
  for (const element of model.elements) {
    const specs = strings(element.metadata.specs);
    if (element.parent === null) {
      byId.set(element.id, entry(element.id, element.id, null, specs));
      continue;
    }
    if (roots.has(element.parent)) {
      byId.set(element.id, toNode(element, element.parent));
      continue;
    }
    const [lang = '', local = '', ...path] = element.id.split('.');
    const node = byId.get(`${lang}.${local}`);
    if (node === undefined) continue;
    const nested = entry(element.id, lang, node.id, specs);
    if (node.virtual) node.hasElements = true;
    else {
      const sep = separator(lang);
      nested.unit = `${node.package}${sep}${path.join(sep)}`;
    }
    byId.set(element.id, nested);
  }
  return new NodeMap([...byId.values()]);
}

/** `lang`'s unit -> element FQN: declared units first-wins in model order, then derived units. */
export function unitToElement(nodeMap: NodeMap, lang: string): Map<string, string> {
  const mapping = new Map<string, string>();
  for (const node of nodeMap.languageNodes(lang)) {
    for (const unit of node.units) if (!mapping.has(unit)) mapping.set(unit, node.id);
  }
  for (const element of nodeMap.languageDerived(lang)) {
    const unit = String(element.unit);
    if (!mapping.has(unit)) mapping.set(unit, element.id);
  }
  return mapping;
}
