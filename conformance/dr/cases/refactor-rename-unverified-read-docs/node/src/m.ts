export class Ds {
  columns: string[] = [];
}

const SECTIONS = ['columns'] as const;

function log(text: string): void {
  console.log(text);
}

export function fill(d: Ds): number {
  let total = 0;
  for (const s of SECTIONS) {
    total += d[s].length;
    log(s);
  }
  return total;
}
