export class Ds {
  columns: string[] = [];
}

export const SECTIONS = ['columns'] as const;

export function read(d: Ds): unknown[] {
  return SECTIONS.map((s) => d[s]);
}
