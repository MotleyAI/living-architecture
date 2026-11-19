// claims-exist and claims-exactly-once: every unit of a language is claimed once and exists, per its facts.
import { message } from 'deterministic-refactor/contract';
import { type Facts, unitFact } from './facts.js';
import { compareStrings } from './order.js';
import { type MapElement, type NodeMap, separator } from './nodes.js';

/** `node`'s declared units, then, when its package is a configured root, that root's top-level units. */
function claimed(node: MapElement, roots: string[], facts: Facts): string[] {
  if (node.package === null || node.package === undefined || !roots.includes(node.package)) return node.units;
  const prefix = `${node.package}${separator(facts.language)}`;
  return [...node.units, ...[...new Set(facts.top_level_units)].filter((u) => u.startsWith(prefix)).sort(compareStrings)];
}

function existenceFindings(node: MapElement, unit: string, facts: Facts): string[] {
  const fact = unitFact(facts, unit);
  if (fact.status === 'missing') return [message('claims-exist.unit-missing', { node: node.id, unit })];
  if (fact.status === 'ambiguous') {
    return [message('claims-exist.unit-ambiguous', { node: node.id, unit, candidates: (fact.candidates ?? []).join(', ') })];
  }
  return [];
}

function declaredFindings(nodeMap: NodeMap, facts: Facts, roots: string[]): string[] {
  const findings: string[] = [];
  const seen = new Map<string, string>();
  for (const node of nodeMap.languageNodes(facts.language)) {
    for (const unit of claimed(node, roots, facts)) {
      if (node.units.includes(unit)) findings.push(...existenceFindings(node, unit, facts));
      const first = seen.get(unit);
      if (first !== undefined) findings.push(message('claims-exactly-once.claimed-twice', { unit, first, second: node.id }));
      else seen.set(unit, node.id);
    }
  }
  for (const unit of [...new Set(facts.top_level_units)].filter((u) => !seen.has(u)).sort(compareStrings)) {
    findings.push(message('claims-exactly-once.unclaimed', { unit }));
  }
  return findings;
}

/** a and b name the same subtree, or one nests inside the other. */
const overlap = (a: string, b: string, sep: string): boolean => a === b || a.startsWith(b + sep) || b.startsWith(a + sep);

function derivedFindings(element: MapElement, candidates: string[], facts: Facts): string[] {
  const findings: string[] = [];
  const sep = separator(facts.language);
  const unit = String(element.unit);
  const clash = candidates.find((c) => overlap(unit, c, sep));
  if (clash !== undefined) findings.push(message('claims-exactly-once.child-collides', { element: element.id, unit, clash }));
  const fact = unitFact(facts, unit);
  if (fact.status === 'missing') findings.push(message('claims-exist.child-missing', { element: element.id, unit }));
  else if (fact.status === 'ambiguous') {
    const candidatesText = (fact.candidates ?? []).join(', ');
    findings.push(message('claims-exist.child-ambiguous', { element: element.id, unit, candidates: candidatesText }));
  }
  return findings;
}

/**
 * One language's declared, then model-derived units: they exist, each top-level unit is claimed once (a node on a
 * configured root claims that root's), and each nests only under its own node.
 */
export function checkClaims(nodeMap: NodeMap, facts: Facts, roots: string[]): string[] {
  const findings = declaredFindings(nodeMap, facts, roots);
  const nodes = nodeMap.languageNodes(facts.language);
  const declared = [...new Set(nodes.flatMap((n) => n.units))].sort(compareStrings);
  for (const node of nodes) {
    if (node.hasElements) findings.push(message('claims-exist.virtual-children', { node: node.id }));
    const candidates = declared.filter((unit) => unit !== node.package);
    for (const element of nodeMap.languageDerived(facts.language)) {
      if (element.node === node.id) findings.push(...derivedFindings(element, candidates, facts));
    }
  }
  return findings;
}
