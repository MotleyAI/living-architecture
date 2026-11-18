export class Ds {
  columns: string[] = [];
}

export class Other {
  columns: number[] = [];
}

const SECTIONS = ['columns'] as const;

function log(text: string): void {
  console.log(text);
}

export function fill(o: Other): number {
  let total = 0;
  for (const s of SECTIONS) {
    total += o[s].length;
    log(s);
  }
  return total;
}
