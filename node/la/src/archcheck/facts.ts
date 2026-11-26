// One language's architecture facts: unit statuses, top-level units and witnessed element edges.
import { requestDocument } from 'type-rename-move/twin';
import { contractHash, identity } from '../contract/index.js';
import { moduleImports, topLevelUnits, unitStatus, type TsLayout } from 'type-rename-move/lang';
import { VERSION } from '../index.js';
import { type NodeMap, unitToElement } from './nodes.js';
import { compareEdge, compareStrings } from './order.js';
import { measureEdges } from './truth.js';

export interface UnitFact {
  unit: string;
  status: 'present' | 'missing' | 'ambiguous';
  candidates?: string[];
}

export interface EdgeFact {
  src: string;
  dst: string;
  src_module: string;
  dst_module: string;
}

/** The facts schema's JSON shape. */
export interface Facts {
  language: string;
  version: string;
  contract_hash: string;
  units: UnitFact[];
  top_level_units: string[];
  edges: EdgeFact[];
}

export function unitFact(facts: Facts, unit: string): UnitFact {
  const found = facts.units.find((u) => u.unit === unit);
  if (found === undefined) throw new Error(`no fact for unit ${unit}`);
  return found;
}

function facts(layout: TsLayout, language: string, units: UnitFact[], attribution: Map<string, string>): Facts {
  const witnesses = measureEdges(moduleImports(layout), attribution, '/');
  return {
    language,
    version: VERSION,
    contract_hash: contractHash(),
    units,
    top_level_units: [...topLevelUnits(layout)].sort(compareStrings),
    edges: [...witnesses]
      .sort(([a], [b]) => compareEdge(a, b))
      .map(([key, [srcModule, dstModule]]) => {
        const [src = '', dst = ''] = key.split('\0');
        return { src, dst, src_module: srcModule, dst_module: dstModule };
      }),
  };
}

/** The TypeScript facts, measured in-process. */
export function nativeFacts(layout: TsLayout, nodeMap: NodeMap, language: string): Facts {
  const units: UnitFact[] = nodeMap.units(language).map((unit) => {
    const { status, candidates } = unitStatus(layout, unit);
    return status === 'ambiguous' ? { unit, status, candidates } : { unit, status };
  });
  return facts(layout, language, units, unitToElement(nodeMap, language));
}

/** The TypeScript facts with edges between top-level units; no model involved. */
export function nativeTopLevelFacts(layout: TsLayout, language: string): Facts {
  return facts(layout, language, [], new Map([...topLevelUnits(layout)].map((unit) => [unit, unit])));
}

function consistent(document: any, expectedUnits: string[], topLevel: boolean): boolean {
  if (!topLevel) {
    const units = new Set<string>(document.units.map((u: { unit: string }) => u.unit));
    return expectedUnits.every((unit) => units.has(unit));
  }
  const tops = new Set<string>(document.top_level_units);
  return document.units.length === 0 && document.edges.every((e: { src: string; dst: string }) => tops.has(e.src) && tops.has(e.dst));
}

/** `language`'s facts from la's twin of it, schema-checked; RelayedFailure or TwinError otherwise. */
export function requestedFacts(language: string, root: string, expectedUnits: string[], topLevel = false): Facts {
  const args = ['--root', root, '--language', language, '--emit', 'facts', ...(topLevel ? ['--top-level'] : [])];
  return requestDocument(language, identity(), 'la-arch-check', args, 'facts', {
    repoRoot: root,
    accept: (document) => consistent(document, expectedUnits, topLevel),
  }) as Facts;
}
