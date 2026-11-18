export class Ds {
  columns: string[] = [];
}

export class Other {
  columns: number[] = [];
}

const SECTIONS = ['columns'] as const;

export function read(o: Other): unknown[] {
  return SECTIONS.map((s) => o[s]);
}
