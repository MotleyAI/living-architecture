// The refactor commands' one line index: TypeScript's line terminators (`\r\n`, `\n`, `\r`, U+2028, U+2029).
const LINE_BREAK = /\r\n|[\n\r\u2028\u2029]/gu;

export class Lines {
  private readonly starts: number[];

  constructor(readonly text: string) {
    this.starts = [0, ...[...text.matchAll(LINE_BREAK)].map((m) => m.index + m[0].length)];
  }

  /** The 1-based line of a UTF-16 position. */
  lineOf(position: number): number {
    let [low, high] = [0, this.starts.length];
    while (low < high) {
      const mid = (low + high) >> 1;
      if ((this.starts[mid] ?? 0) <= position) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  /** The number of lines; a final terminator opens none. */
  get count(): number {
    return this.starts.at(-1) === this.text.length ? this.starts.length - 1 : this.starts.length;
  }

  /** The UTF-16 position of a 1-based line's first character. */
  start(line: number): number {
    return this.starts[line - 1] ?? this.text.length;
  }

  /** A 1-based line's text without its terminator. */
  lineText(line: number): string {
    return this.text.slice(this.start(line), this.start(line + 1)).replace(/(?:\r\n|[\n\r\u2028\u2029])$/u, '');
  }
}
