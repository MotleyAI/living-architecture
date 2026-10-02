// enforced-tags: every arc42 principle item carries a well-formed status tag; `[lang:]` names a declared language.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { checkIds, fullMatch, message, splitLines } from '../contract/index.js';
import { arc42Docs } from './docs.js';

const TAG_RE = /\[(enforced|review|target|lang)(?![\p{L}\p{N}_])([^\]]*)\]/gu;
const TAG_START_RE = /\[(enforced|review|target|lang)(?![\p{L}\p{N}_])/gu;
const FENCE_RE = /^(?:`{3,}|~{3,})/;
const FENCE_FULL_RE = /^(?:`{3,}|~{3,})$/;
const PRINCIPLE_ITEM_RE = /^( {0,3})(\p{Nd}+)\.\s/u;

interface Context {
  issueKeyPattern: string;
  languages: string[];
}

/** Tag id from ': <id>'; null when malformed (no colon, empty, or multi-line). */
function parseTagId(rest: string): string | null {
  if (!rest.startsWith(':')) return null;
  const tagId = rest.slice(1).trim();
  return !tagId || tagId.includes('\n') ? null : tagId;
}

/** [counts as status coverage, findings] for one bracket tag. */
function tagOccurrence(kind: string, rest: string, doc: string, ctx: Context): [boolean, string[]] {
  if (kind === 'review') return rest ? [false, [message('enforced-tags.malformed-review', { doc })]] : [true, []];
  const tagId = parseTagId(rest);
  if (tagId === null) return [false, [message('enforced-tags.malformed', { kind, doc })]];
  if (kind === 'lang') {
    return ctx.languages.includes(tagId) ? [false, []] : [false, [message('enforced-tags.unknown-language', { doc, language: tagId })]];
  }
  if (kind === 'target') {
    if (!fullMatch(ctx.issueKeyPattern, tagId)) {
      return [false, [message('enforced-tags.target-mismatch', { doc, tag_id: tagId, pattern: ctx.issueKeyPattern })]];
    }
    return [true, []];
  }
  if (tagId.startsWith('test:') && tagId !== 'test:') return [true, []];
  if (tagId.startsWith('arch_check:') && checkIds().includes(tagId.slice('arch_check:'.length))) return [true, []];
  return [false, [message('enforced-tags.unknown-id', { doc, tag_id: tagId })]];
}

/** Blank out fenced code blocks so tags and numbered items inside are ignored. */
function stripFences(text: string): string {
  const out: string[] = [];
  let fence = '';
  for (const line of splitLines(text)) {
    if (!fence) {
      const m = FENCE_RE.exec(line.trimStart());
      if (m !== null) fence = m[0];
      out.push(m !== null ? '' : line);
    } else {
      const m = FENCE_FULL_RE.exec(line.trim());
      if (m !== null && m[0][0] === fence[0] && m[0].length >= fence.length) fence = '';
      out.push('');
    }
  }
  return out.join('\n');
}

/** Top-level numbered items as [number, item text incl. continuation lines]. */
function principleItems(text: string): [string, string][] {
  const items: [string, string][] = [];
  let openCol = -1;
  for (const line of splitLines(text)) {
    const m = PRINCIPLE_ITEM_RE.exec(line);
    const [, indent = '', number = ''] = m ?? [];
    const last = items[items.length - 1];
    if (m !== null && !(openCol >= 0 && indent.length >= openCol)) {
      items.push([number, line]);
      openCol = indent.length + number.length + 2;
    } else if (openCol >= 0 && line.trim() && !line.startsWith('#') && last !== undefined) {
      last[1] += `\n${line}`;
    } else {
      openCol = -1;
    }
  }
  return items;
}

/** Python's read_text: universal newlines. */
function readText(path: string): string {
  return readFileSync(path, 'utf8').replace(/\r\n?/g, '\n');
}

export function checkEnforcedTags(root: string, issueKeyPattern: string, languages: string[]): string[] {
  const ctx: Context = { issueKeyPattern, languages };
  const findings: string[] = [];
  for (const name of arc42Docs(root)) {
    const text = stripFences(readText(join(root, 'architecture', name)));
    const occurrences = [...text.matchAll(TAG_RE)];
    const starts = [...text.matchAll(TAG_START_RE)];
    for (const kind of ['enforced', 'review', 'target', 'lang']) {
      const opened = starts.filter((m) => m[1] === kind).length;
      const closed = occurrences.filter((m) => m[1] === kind).length;
      if (opened !== closed) findings.push(message('enforced-tags.malformed', { kind, doc: name }));
    }
    for (const m of occurrences) findings.push(...tagOccurrence(m[1] ?? '', m[2] ?? '', name, ctx)[1]);
    for (const [number, body] of principleItems(text)) {
      const tags = [...body.matchAll(TAG_RE)];
      if (tags.filter((t) => t[1] === 'lang').length > 1) findings.push(message('enforced-tags.malformed', { kind: 'lang', doc: name }));
      if (!tags.some((t) => tagOccurrence(t[1] ?? '', t[2] ?? '', name, ctx)[0])) {
        findings.push(message('enforced-tags.untagged-item', { doc: name, number }));
      }
    }
  }
  return findings;
}
