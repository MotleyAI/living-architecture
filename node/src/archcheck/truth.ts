// model-truth: the model's arrows equal the measured runtime import edges.
import { isOrAncestor } from '../c4/index.js';
import { message } from '../contract/index.js';
import type { ModuleImports } from '../lang/index.js';
import { compareEdge, compareStrings } from './order.js';

/** Element edge key `src\0dst` -> its first witness [importing module, imported module]. */
export type Witnesses = Map<string, [string, string]>;

/** The finest declared element a module belongs to (longest unit prefix), or null. */
function attribute(module: string, units: Map<string, string>, sep: string): string | null {
  let best: string | null = null;
  for (const unit of units.keys()) {
    if ((module === unit || module.startsWith(unit + sep)) && (best === null || unit.length > best.length)) best = unit;
  }
  return best === null ? null : (units.get(best) ?? null);
}

/** Self-pairs and ancestor<->descendant pairs are internal plumbing, never governed by arrows. */
function internal(src: string, dst: string): boolean {
  return isOrAncestor(src, dst) || isOrAncestor(dst, src);
}

/** Element-level edges -> the first witness, over sources and targets in sorted module-id order. */
export function measureEdges(modules: ModuleImports[], units: Map<string, string>, sep: string): Witnesses {
  const witnesses: Witnesses = new Map();
  for (const source of [...modules].sort((a, b) => compareStrings(a.module, b.module))) {
    const src = attribute(source.module, units, sep);
    if (src === null) continue;
    for (const target of [...new Set(source.targets)].sort(compareStrings)) {
      const dst = attribute(target, units, sep);
      if (dst === null || internal(src, dst)) continue;
      const key = `${src}\0${dst}`;
      if (!witnesses.has(key)) witnesses.set(key, [source.module, target]);
    }
  }
  return witnesses;
}

type Pair = [string, string];

const covers = (arrow: Pair, edge: Pair): boolean => isOrAncestor(arrow[0], edge[0]) && isOrAncestor(arrow[1], edge[1]);

/** a is strictly more specific than b: descends from b on both endpoints, and differs. */
const moreSpecific = (a: Pair, b: Pair): boolean =>
  (a[0] !== b[0] || a[1] !== b[1]) && isOrAncestor(b[0], a[0]) && isOrAncestor(b[1], a[1]);

/** An arrow is live iff it is a most-specific cover of at least one measured edge. */
function arrowIsLive(arrow: Pair, edges: Pair[], arrows: Pair[]): boolean {
  return edges
    .filter((edge) => covers(arrow, edge))
    .some((edge) => !arrows.filter((a) => covers(a, edge)).some((a) => moreSpecific(a, arrow)));
}

/** Measured edges (every language's) against every arrow: missing edges sorted, then arrows in model order. */
export function checkModelTruth(witnesses: Witnesses, arrows: Pair[]): string[] {
  const edges: Pair[] = [...witnesses.keys()].map((key) => key.split('\0') as Pair);
  const findings: string[] = [];
  const valid = arrows.filter(([src, dst]) => !internal(src, dst));
  for (const [src, dst] of arrows) if (internal(src, dst)) findings.push(message('model-truth.internal-arrow', { src, dst }));
  for (const key of [...witnesses.keys()].sort(compareEdge)) {
    const edge = key.split('\0') as Pair;
    if (!valid.some((arrow) => covers(arrow, edge))) {
      const [srcModule, dstModule] = witnesses.get(key) ?? ['', ''];
      findings.push(
        message('model-truth.missing-edge', { src: edge[0], dst: edge[1], src_module: srcModule, dst_module: dstModule }),
      );
    }
  }
  for (const arrow of valid) {
    if (!edges.some((edge) => covers(arrow, edge))) findings.push(message('model-truth.dead', { src: arrow[0], dst: arrow[1] }));
    else if (!arrowIsLive(arrow, edges, valid)) findings.push(message('model-truth.shadowed', { src: arrow[0], dst: arrow[1] }));
  }
  return findings;
}
