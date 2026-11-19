// arc42-exists, spec-mapping and baseline-ratchet (all read from the repo root).
import { existsSync, readdirSync, statSync } from 'node:fs';
import { basename, isAbsolute, join } from 'node:path';
import { ARCH_DIR, DOC_SUFFIX, architectureFiles, elementDoc, isFlatDoc } from '../c4/index.js';
import { message } from '../contract/index.js';
import type { Index } from './index-file.js';
import type { NodeMap } from './nodes.js';
import { compareStrings } from './order.js';

export const SYSTEM_DOC = `${ARCH_DIR}system${DOC_SUFFIX}`;

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
  return existsSync(dir) ? readdirSync(dir).filter((name) => name.endsWith(DOC_SUFFIX)).sort(compareStrings) : [];
}

function crossCuttingFindings(root: string, entry: string, elementDocs: Map<string, string>): string[] {
  const findings: string[] = [];
  if (!isFlatDoc(entry)) findings.push(message('arc42-exists.cross-cutting-not-flat', { doc: entry }));
  if (!isFile(under(root, entry))) findings.push(message('arc42-exists.cross-cutting-missing', { doc: entry }));
  const element = elementDocs.get(entry);
  if (element !== undefined) findings.push(message('arc42-exists.cross-cutting-is-element', { doc: entry, element }));
  return findings;
}

export function checkArc42(root: string, index: Index, nodeMap: NodeMap): string[] {
  const findings: string[] = [];
  if (!isFile(join(root, SYSTEM_DOC))) findings.push(message('arc42-exists.system-missing', { doc: SYSTEM_DOC }));
  const elementDocs = new Map(nodeMap.elements.map((e) => [elementDoc(e.id), e.id]));
  const entries = (index.get('cross_cutting_arc42') ?? []) as string[];
  for (const entry of entries) findings.push(...crossCuttingFindings(root, entry, elementDocs));
  for (const doc of architectureFiles(root, [DOC_SUFFIX])) {
    if (doc.slice(ARCH_DIR.length).includes('/')) findings.push(message('arc42-exists.nested-doc', { doc }));
  }
  const registered = new Set([SYSTEM_DOC, ...elementDocs.keys(), ...entries]);
  for (const name of arc42Docs(root)) {
    const rel = `${ARCH_DIR}${name}`;
    if (!registered.has(rel)) findings.push(message('arc42-exists.orphan', { doc: rel, system: SYSTEM_DOC }));
  }
  return findings;
}

/** Spec group -> owning element (or cross_cutting_specs), appending duplicate-mapping findings. */
function mappedSpecGroups(index: Index, nodeMap: NodeMap, findings: string[]): Map<string, string> {
  const elements = nodeMap.elementIds();
  const mapped = new Map<string, string>();
  for (const element of nodeMap.elements) {
    for (const group of element.specs) {
      const first = mapped.get(group);
      if (first !== undefined) findings.push(message('spec-mapping.mapped-twice', { group, first, second: element.id }));
      mapped.set(group, element.id);
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
      if (!elements.has(touched)) findings.push(message('spec-mapping.unknown-element', { group, element: touched }));
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
