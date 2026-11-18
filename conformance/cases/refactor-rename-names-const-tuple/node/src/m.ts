export class Ds {
  columns: string[] = [];
}

const SECTIONS = ['columns'] as const;

export function read(d: Ds): unknown[] {
  const out: unknown[] = SECTIONS.map((s) => d[s]);
  for (const s of SECTIONS) {
    out.push(Reflect.get(d, s));
  }
  return out;
}
