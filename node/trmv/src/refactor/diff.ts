// The unified diff rope prints: Python difflib's SequenceMatcher (autojunk on) and unified_diff, ported.

type Block = [number, number, number];
type Opcode = [string, number, number, number, number];

const CONTEXT = 3;
// eslint-disable-next-line no-control-regex -- Python's str.splitlines breaks on these
const LINE = /[^\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]*(?:\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029])?/gu;

/** Python's str.splitlines(keepends=True). */
function lines(text: string): string[] {
  return [...text.matchAll(LINE)].map((m) => m[0]).filter((line) => line !== '');
}

/** The opcode tag for a gap that skips `a` lines (`inA`) and/or `b` lines (`inB`); null when neither. */
function changeTag(inA: boolean, inB: boolean): string | null {
  if (inA && inB) return 'replace';
  if (inA) return 'delete';
  return inB ? 'insert' : null;
}

class SequenceMatcher {
  private readonly b2j = new Map<string, number[]>();

  constructor(
    private readonly a: string[],
    private readonly b: string[],
  ) {
    b.forEach((elt, j) => {
      const indices = this.b2j.get(elt) ?? [];
      indices.push(j);
      this.b2j.set(elt, indices);
    });
    if (b.length >= 200) {
      const ntest = Math.floor(b.length / 100) + 1;
      for (const [elt, indices] of this.b2j) if (indices.length > ntest) this.b2j.delete(elt);
    }
  }

  /** The longest junk-free match in a[alo:ahi] × b[blo:bhi], before extension. */
  private longestRawMatch(alo: number, ahi: number, blo: number, bhi: number): Block {
    let best: Block = [alo, blo, 0];
    let j2len = new Map<number, number>();
    for (let i = alo; i < ahi; i++) {
      const next = new Map<number, number>();
      for (const j of this.b2j.get(this.a[i] ?? '') ?? []) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) ?? 0) + 1;
        next.set(j, k);
        if (k > best[2]) best = [i - k + 1, j - k + 1, k];
      }
      j2len = next;
    }
    return best;
  }

  private longestMatch(alo: number, ahi: number, blo: number, bhi: number): Block {
    const { a, b } = this;
    let [besti, bestj, bestsize] = this.longestRawMatch(alo, ahi, blo, bhi);
    while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) [besti, bestj, bestsize] = [besti - 1, bestj - 1, bestsize + 1];
    while (besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] === b[bestj + bestsize]) bestsize++;
    return [besti, bestj, bestsize];
  }

  private matchingBlocks(): Block[] {
    const queue: [number, number, number, number][] = [[0, this.a.length, 0, this.b.length]];
    const blocks: Block[] = [];
    while (queue.length > 0) {
      const [alo, ahi, blo, bhi] = queue.pop() as [number, number, number, number];
      const [i, j, k] = this.longestMatch(alo, ahi, blo, bhi);
      if (k === 0) continue;
      blocks.push([i, j, k]);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
    blocks.sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2]);
    return this.coalesced(blocks);
  }

  /** Adjacent blocks merged, then the (len(a), len(b), 0) sentinel. */
  private coalesced(blocks: Block[]): Block[] {
    const out: Block[] = [];
    let [i1, j1, k1] = [0, 0, 0];
    for (const [i2, j2, k2] of blocks) {
      if (i1 + k1 === i2 && j1 + k1 === j2) {
        k1 += k2;
      } else {
        if (k1 > 0) out.push([i1, j1, k1]);
        [i1, j1, k1] = [i2, j2, k2];
      }
    }
    if (k1 > 0) out.push([i1, j1, k1]);
    out.push([this.a.length, this.b.length, 0]);
    return out;
  }

  private opcodes(): Opcode[] {
    const out: Opcode[] = [];
    let [i, j] = [0, 0];
    for (const [ai, bj, size] of this.matchingBlocks()) {
      const tag = changeTag(i < ai, j < bj);
      if (tag !== null) out.push([tag, i, ai, j, bj]);
      [i, j] = [ai + size, bj + size];
      if (size > 0) out.push(['equal', ai, i, bj, j]);
    }
    return out;
  }

  groupedOpcodes(n: number): Opcode[][] {
    const codes = this.opcodes();
    if (codes.length === 0) codes.push(['equal', 0, 1, 0, 1]);
    const first = codes[0] as Opcode;
    if (first[0] === 'equal') codes[0] = ['equal', Math.max(first[1], first[2] - n), first[2], Math.max(first[3], first[4] - n), first[4]];
    const last = codes.at(-1) as Opcode;
    if (last[0] === 'equal') {
      codes[codes.length - 1] = ['equal', last[1], Math.min(last[2], last[1] + n), last[3], Math.min(last[4], last[3] + n)];
    }
    const groups: Opcode[][] = [];
    let group: Opcode[] = [];
    for (const [tag, i1, i2, j1, j2] of codes) {
      let [from1, from2] = [i1, j1];
      if (tag === 'equal' && i2 - i1 > 2 * n) {
        group.push([tag, i1, Math.min(i2, i1 + n), j1, Math.min(j2, j1 + n)]);
        groups.push(group);
        group = [];
        [from1, from2] = [Math.max(i1, i2 - n), Math.max(j1, j2 - n)];
      }
      group.push([tag, from1, i2, from2, j2]);
    }
    if (group.length > 0 && !(group.length === 1 && group[0]?.[0] === 'equal')) groups.push(group);
    return groups;
  }
}

function range(start: number, stop: number): string {
  const length = stop - start;
  if (length === 1) return `${start + 1}`;
  return `${length === 0 ? start : start + 1},${length}`;
}

/** The diff of one file as rope prints it: `a/`/`b/` labels, three context lines, no end-of-file marker. */
export function unifiedDiff(oldText: string, newText: string, path: string): string {
  const [a, b] = [lines(oldText), lines(newText)];
  const groups = new SequenceMatcher(a, b).groupedOpcodes(CONTEXT);
  if (groups.length === 0) return '';
  let out = `--- a/${path}\n+++ b/${path}\n`;
  for (const group of groups) {
    const [first, last] = [group[0] as Opcode, group.at(-1) as Opcode];
    out += `@@ -${range(first[1], last[2])} +${range(first[3], last[4])} @@\n`;
    for (const [tag, i1, i2, j1, j2] of group) {
      if (tag === 'equal') {
        out += a.slice(i1, i2).map((line) => ` ${line}`).join('');
        continue;
      }
      if (tag !== 'insert') out += a.slice(i1, i2).map((line) => `-${line}`).join('');
      if (tag !== 'delete') out += b.slice(j1, j2).map((line) => `+${line}`).join('');
    }
  }
  return out;
}
