// The canonical node/unit map: one root per language, nodes from model metadata, nested elements by convention.
import type { Element, ModelParse } from '../c4/index.js';
import { language, message, schema, validate } from '../contract/index.js';
import { ArchCheckError } from './index-file.js';

/** A child of a language root; `units` are its declared units in metadata order. */
export interface Node {
  id: string;
  language: string;
  virtual: boolean;
  package: string | null;
  units: string[];
  arc42: string | null;
  specs: string[];
  hasElements: boolean;
}

/** An element nested under a precise node and the unit it maps to by convention. */
export interface Derived {
  id: string;
  node: string;
  language: string;
  unit: string;
}

export class NodeMap {
  constructor(
    readonly nodes: Node[],
    readonly derived: Derived[],
  ) {}

  nodeIds(): Set<string> {
    return new Set(this.nodes.map((n) => n.id));
  }

  languageNodes(lang: string): Node[] {
    return this.nodes.filter((n) => n.language === lang);
  }

  languageDerived(lang: string): Derived[] {
    return this.derived.filter((d) => d.language === lang);
  }

  /** Every declared, then derived unit of `lang`, in model order, each once. */
  units(lang: string): string[] {
    const all = [...this.languageNodes(lang).flatMap((n) => n.units), ...this.languageDerived(lang).map((d) => d.unit)];
    return [...new Set(all)];
  }
}

export function separator(lang: string): string {
  return language(lang).unit_separator;
}

function metadataErrors(element: Element): string[] {
  const variety = element.virtual ? 'virtual' : 'precise';
  const errors = validate({ ...schema('node'), $ref: `#/$defs/${variety}` }, element.metadata);
  return errors.map((error) => message('arch-check.metadata-invalid', { element: element.id, error }));
}

const strings = (value: unknown): string[] => (Array.isArray(value) ? value.map(String) : []);

function toNode(element: Element, lang: string): Node {
  const meta = element.metadata;
  const pkg = meta.package;
  const units = element.virtual ? strings(meta.packages) : [String(pkg), ...strings(meta.claims)];
  return {
    id: element.id,
    language: lang,
    virtual: element.virtual,
    package: typeof pkg === 'string' ? pkg : null,
    units,
    arc42: typeof meta.arc42 === 'string' ? meta.arc42 : null,
    specs: strings(meta.specs),
    hasElements: false,
  };
}

function problems(model: ModelParse, languages: string[]): string[] {
  const out: string[] = [];
  const roots = new Set(model.elements.filter((e) => e.parent === null).map((e) => e.id));
  for (const element of model.elements) {
    if (element.parent === null) {
      if (!languages.includes(element.id)) out.push(message('arch-check.root-undeclared', { element: element.id }));
      else if (element.hasMetadata || element.metadataProblems.length > 0) {
        out.push(message('arch-check.metadata-on-root', { element: element.id }));
      }
    } else if (element.metadataProblems.length > 0) out.push(...element.metadataProblems);
    else if (!roots.has(element.parent)) {
      if (element.hasMetadata) out.push(message('arch-check.metadata-on-nested', { element: element.id }));
    } else out.push(...metadataErrors(element));
  }
  for (const lang of languages) if (!roots.has(lang)) out.push(message('arch-check.root-missing', { language: lang }));
  return out;
}

/** The map for `model`; ArchCheckError naming every root and metadata problem, in model order. */
export function buildNodeMap(model: ModelParse, languages: string[]): NodeMap {
  const found = problems(model, languages);
  if (found.length > 0) throw new ArchCheckError(found.join('; '));
  const roots = new Set(model.elements.filter((e) => e.parent === null).map((e) => e.id));
  const nodes = new Map<string, Node>();
  for (const e of model.elements) if (e.parent !== null && roots.has(e.parent)) nodes.set(e.id, toNode(e, e.parent));
  const derived: Derived[] = [];
  for (const element of model.elements) {
    if (element.parent === null || roots.has(element.parent)) continue;
    const [lang = '', local = '', ...path] = element.id.split('.');
    const node = nodes.get(`${lang}.${local}`);
    if (node === undefined) continue;
    if (node.virtual) node.hasElements = true;
    else {
      const sep = separator(lang);
      derived.push({ id: element.id, node: node.id, language: lang, unit: `${node.package}${sep}${path.join(sep)}` });
    }
  }
  return new NodeMap([...nodes.values()], derived);
}

/** `lang`'s unit -> element FQN: declared units first-wins in model order, then derived units. */
export function unitToElement(nodeMap: NodeMap, lang: string): Map<string, string> {
  const mapping = new Map<string, string>();
  for (const node of nodeMap.languageNodes(lang)) {
    for (const unit of node.units) if (!mapping.has(unit)) mapping.set(unit, node.id);
  }
  for (const element of nodeMap.languageDerived(lang)) if (!mapping.has(element.unit)) mapping.set(element.unit, element.id);
  return mapping;
}
