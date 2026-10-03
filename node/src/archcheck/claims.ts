// claims-exist and claims-exactly-once: every unit of a language is claimed once and exists, per its facts.
import { message } from '../contract/index.js';
import { type Facts, unitFact } from './facts.js';
import { compareStrings } from './order.js';
import { type Derived, type NodeMap, separator } from './nodes.js';

function declaredFindings(nodeMap: NodeMap, facts: Facts): string[] {
  const findings: string[] = [];
  const seen = new Map<string, string>();
  for (const node of nodeMap.languageNodes(facts.language)) {
    for (const unit of node.units) {
      const fact = unitFact(facts, unit);
      if (fact.status === 'missing') findings.push(message('claims-exist.unit-missing', { node: node.id, unit }));
      else if (fact.status === 'ambiguous') {
        const candidates = (fact.candidates ?? []).join(', ');
        findings.push(message('claims-exist.unit-ambiguous', { node: node.id, unit, candidates }));
      }
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

function derivedFindings(element: Derived, candidates: string[], facts: Facts): string[] {
  const findings: string[] = [];
  const sep = separator(facts.language);
  const clash = candidates.find((c) => overlap(element.unit, c, sep));
  if (clash !== undefined) {
    findings.push(message('claims-exactly-once.child-collides', { element: element.id, unit: element.unit, clash }));
  }
  const fact = unitFact(facts, element.unit);
  if (fact.status === 'missing') findings.push(message('claims-exist.child-missing', { element: element.id, unit: element.unit }));
  else if (fact.status === 'ambiguous') {
    const candidatesText = (fact.candidates ?? []).join(', ');
    findings.push(message('claims-exist.child-ambiguous', { element: element.id, unit: element.unit, candidates: candidatesText }));
  }
  return findings;
}

/** One language's declared, then model-derived units: they exist, and each nests only under its own node. */
export function checkClaims(nodeMap: NodeMap, facts: Facts): string[] {
  const findings = declaredFindings(nodeMap, facts);
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
