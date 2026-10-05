// arc42-exists, spec-mapping and baseline-ratchet (all read from the repo root).
import { existsSync, readdirSync, statSync } from 'node:fs';
import { basename, isAbsolute, join } from 'node:path';
import { message } from '../contract/index.js';
import type { Index } from './index-file.js';
import type { NodeMap } from './nodes.js';
import { compareStrings } from './order.js';

export const SYSTEM_DOC = 'architecture/system.arc42.md';

/** `root / rel` as pathlib joins it: an absolute `rel` wins. */
const under = (root: string, rel: string): string => (isAbsolute(rel) ? rel : join(root, rel));

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function isDir(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/** `architecture/*.arc42.md`, sorted. */
export function arc42Docs(root: string): string[] {
  const dir = join(root, 'architecture');
  return existsSync(dir) ? readdirSync(dir).filter((name) => name.endsWith('.arc42.md')).sort(compareStrings) : [];
}

export function checkArc42(root: string, index: Index, nodeMap: NodeMap): string[] {
  const findings: string[] = [];
  if (!isFile(join(root, SYSTEM_DOC))) findings.push(message('arc42-exists.system-missing', { doc: SYSTEM_DOC }));
  const registered = new Set([SYSTEM_DOC]);
  for (const node of nodeMap.nodes) {
    if (node.arc42) {
      registered.add(node.arc42);
      if (!isFile(under(root, node.arc42))) findings.push(message('arc42-exists.node-doc-missing', { node: node.id, doc: node.arc42 }));
    }
  }
  for (const entry of (index.get('cross_cutting_arc42') ?? []) as string[]) {
    registered.add(entry);
    if (!isFile(under(root, entry))) findings.push(message('arc42-exists.cross-cutting-missing', { doc: entry }));
  }
  for (const name of arc42Docs(root)) {
    const rel = `architecture/${name}`;
    if (!registered.has(rel)) findings.push(message('arc42-exists.orphan', { doc: rel, system: SYSTEM_DOC }));
  }
  return findings;
}

/** Spec group -> owning node (or cross_cutting_specs), appending duplicate-mapping findings. */
function mappedSpecGroups(index: Index, nodeMap: NodeMap, findings: string[]): Map<string, string> {
  const nodes = nodeMap.nodeIds();
  const mapped = new Map<string, string>();
  for (const node of nodeMap.nodes) {
    for (const group of node.specs) {
      const first = mapped.get(group);
      if (first !== undefined) findings.push(message('spec-mapping.mapped-twice', { group, first, second: node.id }));
      mapped.set(group, node.id);
    }
  }
  const crossCutting = (index.get('cross_cutting_specs') ?? new Map()) as Map<string, Map<string, unknown> | null>;
  for (const [group, spec] of crossCutting) {
    const first = mapped.get(group);
    if (first !== undefined) {
      findings.push(message('spec-mapping.mapped-twice', { group, first, second: 'cross_cutting_specs' }));
    }
    mapped.set(group, 'cross_cutting_specs');
    for (const touched of (spec?.get('touches') ?? []) as string[]) {
      if (!nodes.has(touched)) findings.push(message('spec-mapping.unknown-node', { group, node: touched }));
    }
  }
  return mapped;
}

function containsSpecMd(dir: string): boolean {
  return readdirSync(dir, { recursive: true, encoding: 'utf8' }).some((entry) => basename(entry) === 'spec.md');
}

function subdirNames(path: string): string[] {
  return isDir(path) ? readdirSync(path).filter((name) => isDir(join(path, name))) : [];
}

/** Spec group -> its dirs under openspec/specs/ and every non-archived change's specs/. */
function presentSpecGroups(root: string): Map<string, string[]> {
  const openspec = join(root, 'openspec');
  const changes = join(openspec, 'changes');
  const specsDirs = [join(openspec, 'specs')];
  for (const change of subdirNames(changes)) if (change !== 'archive') specsDirs.push(join(changes, change, 'specs'));
  const present = new Map<string, string[]>();
  for (const specsDir of specsDirs) {
    for (const group of subdirNames(specsDir)) present.set(group, [...(present.get(group) ?? []), join(specsDir, group)]);
  }
  return present;
}

export function checkSpecMapping(root: string, index: Index, nodeMap: NodeMap): string[] {
  const findings: string[] = [];
  const mapped = mappedSpecGroups(index, nodeMap, findings);
  const present = presentSpecGroups(root);
  for (const group of [...present.keys()].filter((g) => !mapped.has(g)).sort(compareStrings)) {
    findings.push(message('spec-mapping.unmapped', { group }));
  }
  for (const group of [...mapped.keys()].filter((g) => !present.has(g)).sort(compareStrings)) {
    findings.push(message('spec-mapping.dir-missing', { group }));
  }
  for (const group of [...mapped.keys()].filter((g) => present.has(g)).sort(compareStrings)) {
    if (!(present.get(group) ?? []).some(containsSpecMd)) findings.push(message('spec-mapping.no-spec-md', { group }));
  }
  return findings;
}

/** The count of `#legacy` arrows in the model must equal the declared baseline (only ever lowered). */
export function checkLegacyRatchet(index: Index, legacyCount: number): string[] {
  const spec = index.get('legacy_arrows');
  if (!(spec instanceof Map) || !spec.has('baseline')) return [message('baseline-ratchet.missing')];
  const baseline = spec.get('baseline');
  const valid = (typeof baseline === 'number' && Number.isInteger(baseline) && baseline >= 0) || (typeof baseline === 'bigint' && baseline >= 0n);
  if (!valid) return [message('baseline-ratchet.invalid', { value: baseline })];
  if (BigInt(legacyCount) !== BigInt(baseline as number | bigint)) {
    return [message('baseline-ratchet.mismatch', { count: legacyCount, baseline })];
  }
  return [];
}
