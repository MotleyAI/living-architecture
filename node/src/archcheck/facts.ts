// One language's architecture facts: unit statuses, top-level units and witnessed element edges.
import { contractHash } from '../contract/index.js';
import { moduleImports, topLevelUnits, unitStatus, type TsLayout } from '../lang/index.js';
import { VERSION } from '../index.js';
import { type NodeMap, unitToElement } from './nodes.js';
import { compareEdge } from './order.js';
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

/** The TypeScript facts, measured in-process. */
export function nativeFacts(layout: TsLayout, nodeMap: NodeMap, language: string): Facts {
  const units: UnitFact[] = nodeMap.units(language).map((unit) => {
    const { status, candidates } = unitStatus(layout, unit);
    return status === 'ambiguous' ? { unit, status, candidates } : { unit, status };
  });
  const witnesses = measureEdges(moduleImports(layout), unitToElement(nodeMap, language), '/');
  return {
    language,
    version: VERSION,
    contract_hash: contractHash(),
    units,
    top_level_units: [...topLevelUnits(layout)].sort(),
    edges: [...witnesses]
      .sort(([a], [b]) => compareEdge(a, b))
      .map(([key, [srcModule, dstModule]]) => {
        const [src = '', dst = ''] = key.split('\0');
        return { src, dst, src_module: srcModule, dst_module: dstModule };
      }),
  };
}
