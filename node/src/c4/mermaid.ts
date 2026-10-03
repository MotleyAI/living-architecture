// Deterministic mermaid rendering of a view.
import { message } from '../contract/index.js';
import type { Element, ModelParse } from './model.js';
import type { View } from './views.js';

const mangle = (eid: string): string => eid.replaceAll('.', '__');
const escapeTitle = (title: string): string => title.replaceAll('"', '#quot;');

function nodeLine(element: Element | undefined, nid: string, indent: number): string {
  const title = escapeTitle(element?.title ?? nid);
  const shape = element?.virtual ? `("${title}")` : `["${title}"]`;
  return `${' '.repeat(indent)}${mangle(nid)}${shape}`;
}

/** Nested subgraphs when children are shown, else flat. */
export function renderMermaid(view: View, model: ModelParse): string {
  const byId = new Map(model.elements.map((e) => [e.id, e]));
  const shown = new Set(view.nodeIds);
  const shownKids = new Map<string, string[]>();
  for (const e of model.elements) {
    if (shown.has(e.id) && e.parent !== null && shown.has(e.parent)) {
      shownKids.set(e.parent, [...(shownKids.get(e.parent) ?? []), e.id]);
    }
  }
  const lines = ['```mermaid', 'flowchart TD', `  %% ${view.id}: ${view.title}`];
  if (shownKids.size > 0) lines.push(...hierarchicalBody(view, byId, shown, shownKids));
  else {
    for (const nid of view.nodeIds) lines.push(nodeLine(byId.get(nid), nid, 2));
    for (const edge of view.edges) lines.push(`  ${edge.src} ${edge.legacy ? '-.->' : '-->'} ${edge.dst}`);
  }
  lines.push('```');
  if (view.edges.some((edge) => edge.legacy)) lines.push(message('c4.legacy-legend'));
  return lines.join('\n');
}

function hierarchicalBody(
  view: View,
  byId: Map<string, Element>,
  shown: Set<string>,
  shownKids: Map<string, string[]>,
): string[] {
  const lines: string[] = [];
  const leaves: string[] = [];
  const emit = (nid: string, indent: number): void => {
    const pad = ' '.repeat(indent);
    const kids = shownKids.get(nid) ?? [];
    if (kids.length > 0) {
      lines.push(`${pad}subgraph ${mangle(nid)}["${escapeTitle(byId.get(nid)?.title ?? nid)}"]`);
      for (const child of kids) emit(child, indent + 2);
      lines.push(`${pad}end`);
    } else {
      leaves.push(mangle(nid));
      lines.push(nodeLine(byId.get(nid), nid, indent));
    }
  };
  for (const eid of view.nodeIds) {
    const element = byId.get(eid);
    if (element === undefined || element.parent === null || !shown.has(element.parent)) emit(eid, 2);
  }
  for (const edge of view.edges) lines.push(`  ${mangle(edge.src)} ${edge.legacy ? '-.->' : '-->'} ${mangle(edge.dst)}`);
  if (leaves.length > 0) lines.push('  classDef leaf fill:none;', `  class ${leaves.join(',')} leaf;`);
  return lines;
}
