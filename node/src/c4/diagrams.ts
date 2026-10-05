// Mermaid blocks in arc42 docs: regeneration (`la-arch-diagrams`) and the diagrams-fresh check.
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { message } from '../contract/index.js';
import { readIndex } from './index-file.js';
import { renderMermaid } from './mermaid.js';
import { type ModelParse, parseModel, project } from './model.js';
import { type View, type ViewsParse, parseViews } from './views.js';

const MARKER_RE = /<!--\s+(\/?)likec4:([\p{L}\p{N}_]+)\s+-->/gu;

/** The mapped docs cannot be regenerated. */
export class DiagramsError extends Error {}

/** Read preserving exact bytes (no newline translation) for byte-for-byte checks. */
function readExact(path: string): string {
  return new TextDecoder('utf-8', { fatal: true }).decode(readFileSync(path));
}

/** pathlib's parts: empty and `.` segments dropped, a leading `/` its own part. */
function pathParts(key: string): string[] {
  const parts = key.split('/').filter((p) => p !== '' && p !== '.');
  return key.startsWith('/') ? ['/', ...parts] : parts;
}

/** True only for a direct architecture/<name>.arc42.md child (rejects traversal/nesting). */
function isArc42DocKey(key: unknown): key is string {
  if (typeof key !== 'string' || !key.endsWith('.arc42.md')) return false;
  const parts = pathParts(key);
  return parts.length === 2 && parts[0] === 'architecture';
}

/** A view's marker-wrapped mermaid block, exactly as la-arch-diagrams writes it. */
export function diagramBlock(view: View, model: ModelParse): string {
  return `<!-- likec4:${view.id} -->\n${renderMermaid(view, project(model, view.root))}\n<!-- /likec4:${view.id} -->`;
}

type Span = [number, number];

/** [span, error]: the open→close span, or null + one of missing/duplicate/order. */
function markerSpan(text: string, vid: string): [Span | null, string | null] {
  const matches = [...text.matchAll(MARKER_RE)].filter((m) => m[2] === vid);
  const opens = matches.filter((m) => !m[1]);
  const closes = matches.filter((m) => m[1]);
  const [open] = opens;
  const [close] = closes;
  if (open === undefined || close === undefined) return [null, 'missing'];
  if (opens.length > 1 || closes.length > 1) return [null, 'duplicate'];
  if (close.index < open.index) return [null, 'order'];
  return [[open.index, close.index + close[0].length], null];
}

/** The index.yaml `diagrams` value, or a message explaining why it is unusable (never throws). */
export function diagramsMap(root: string): unknown {
  const index = readIndex(root);
  if (typeof index === 'string') return index;
  const diagrams = index.get('diagrams');
  return diagrams === undefined || diagrams === null ? message('c4.no-diagrams-block') : diagrams;
}

function badDiagramsReason(diagrams: unknown): string {
  return typeof diagrams === 'string' ? diagrams : message('c4.diagrams-not-mapping');
}

/** Python iteration of a YAML value: a string by character, a mapping by key. */
function iterate(value: unknown): unknown[] {
  if (typeof value === 'string') return [...value];
  if (Array.isArray(value)) return value;
  if (value instanceof Map) return [...value.keys()];
  throw new DiagramsError(`'${typeof value}' object is not iterable`);
}

/** Rewrite every mapped view's marker block in one doc's text; throw on a missing view or marker. */
function rewriteMarkers(text: string, vids: unknown, byId: Map<unknown, View>, model: ModelParse, docKey: string): string {
  let out = text;
  for (const vid of iterate(vids)) {
    const view = byId.get(vid);
    if (view === undefined) throw new DiagramsError(message('arch-diagrams.view-undefined', { view: vid, doc: docKey }));
    const [span, error] = markerSpan(out, view.id);
    if (error !== null || span === null) {
      throw new DiagramsError(message('arch-diagrams.marker', { doc: docKey, problem: error, view: vid }));
    }
    out = out.slice(0, span[0]) + diagramBlock(view, model) + out.slice(span[1]);
  }
  return out;
}

/** Rewrite each mapped doc's marker blocks from the model; return changed repo-relative paths. */
export function generate(root: string): string[] {
  const diagrams = diagramsMap(root);
  if (!(diagrams instanceof Map)) throw new DiagramsError(badDiagramsReason(diagrams));
  const model = parseModel(root);
  const views = parseViews(root, model);
  const problems = [...model.findings, ...model.metadataFindings, ...views.findings];
  if (problems.length > 0) throw new DiagramsError(message('arch-diagrams.parse-findings', { findings: problems.join('\n') }));
  const byId = new Map<unknown, View>(views.views.map((v) => [v.id, v]));
  const changed: string[] = [];
  for (const [docKey, vids] of diagrams) {
    if (!isArc42DocKey(docKey)) throw new DiagramsError(message('arch-diagrams.bad-key', { key: docKey }));
    const docPath = join(root, docKey);
    const text = readExact(docPath);
    const newText = rewriteMarkers(text, vids, byId, model, docKey);
    if (newText !== text) {
      writeFileSync(docPath, newText, 'utf8');
      changed.push(docKey);
    }
  }
  return changed;
}

/** `la-arch-diagrams`: print each rewritten doc. */
export function run(root: string): number {
  let changed: string[];
  try {
    changed = generate(root);
  } catch (error) {
    process.stderr.write(`${message('arch-diagrams.error', { error: (error as Error).message })}\n`);
    return 1;
  }
  for (const docKey of changed) process.stdout.write(`${docKey}\n`);
  return 0;
}

function validateEntry(docKey: unknown, vids: unknown): [string[], string[] | null] {
  if (!isArc42DocKey(docKey)) return [[message('diagrams-fresh.bad-key', { key: docKey })], null];
  if (!Array.isArray(vids)) return [[message('diagrams-fresh.not-a-list', { key: docKey })], null];
  if (vids.length === 0) return [[message('diagrams-fresh.empty', { key: docKey })], null];
  const findings: string[] = [];
  const seen = new Set<string>();
  const valid: string[] = [];
  let ok = true;
  for (const vid of vids) {
    if (typeof vid !== 'string' || !vid) {
      findings.push(message('diagrams-fresh.invalid-view-id', { key: docKey, view: vid }));
      ok = false;
    } else if (seen.has(vid)) {
      findings.push(message('diagrams-fresh.duplicate-view-id', { key: docKey, view: vid }));
      ok = false;
    } else {
      seen.add(vid);
      valid.push(vid);
    }
  }
  return [findings, ok ? valid : null];
}

/** Validated doc -> view-ids mapping; appends schema findings, fail-closed on bad input. */
function collectMapping(diagrams: unknown, findings: string[]): Map<string, string[]> {
  const mapping = new Map<string, string[]>();
  if (!(diagrams instanceof Map)) {
    findings.push(message('diagrams-fresh.unusable', { reason: badDiagramsReason(diagrams) }));
    return mapping;
  }
  for (const [docKey, vids] of diagrams) {
    const [entryFindings, valid] = validateEntry(docKey, vids);
    findings.push(...entryFindings);
    if (valid !== null) mapping.set(docKey as string, valid);
  }
  return mapping;
}

function checkFreshness(root: string, model: ModelParse, views: ViewsParse, mapping: Map<string, string[]>): string[] {
  const byId = new Map(views.views.map((v) => [v.id, v]));
  const findings: string[] = [];
  for (const [docKey, vids] of mapping) {
    const docPath = join(root, docKey);
    if (!existsSync(docPath)) {
      findings.push(message('diagrams-fresh.doc-missing', { doc: docKey }));
      continue;
    }
    const text = readExact(docPath);
    for (const vid of vids) {
      const view = byId.get(vid);
      if (view === undefined) {
        findings.push(message('diagrams-fresh.view-unknown', { view: vid, doc: docKey }));
        continue;
      }
      const [span, error] = markerSpan(text, vid);
      if (error !== null) findings.push(message(`diagrams-fresh.marker-${error}`, { doc: docKey, view: vid }));
      else if (span !== null && text.slice(span[0], span[1]) !== diagramBlock(view, model)) {
        findings.push(message('diagrams-fresh.stale', { doc: docKey, view: vid }));
      }
    }
  }
  return findings;
}

function checkOrphanMarkers(root: string, mapping: Map<string, string[]>): string[] {
  const findings: string[] = [];
  const dir = join(root, 'architecture');
  const docs = existsSync(dir) ? readdirSync(dir).filter((name) => name.endsWith('.arc42.md')).sort() : [];
  for (const name of docs) {
    const docKey = `architecture/${name}`;
    const mapped = new Set(mapping.get(docKey) ?? []);
    for (const m of readExact(join(dir, name)).matchAll(MARKER_RE)) {
      const vid = m[2] ?? '';
      if (mapped.has(vid)) continue;
      const kind = m[1] === '/' ? 'closing' : 'opening';
      findings.push(message('diagrams-fresh.orphan-marker', { doc: docKey, kind, view: vid }));
    }
  }
  return findings;
}

/** Fail-closed freshness check surfaced by the arch-check; never throws on malformed input. */
export function checkDiagramsFresh(root: string, model: ModelParse, views: ViewsParse): string[] {
  const findings = [...model.findings, ...views.findings].map((finding) => message('diagrams-fresh.parse', { finding }));
  const mapping = collectMapping(diagramsMap(root), findings);
  findings.push(...checkFreshness(root, model, views, mapping));
  findings.push(...checkOrphanMarkers(root, mapping));
  return findings;
}
