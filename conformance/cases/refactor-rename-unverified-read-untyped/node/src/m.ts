export class Ds {
  columns: string[] = [];
}

const SECTIONS = ['columns'] as const;

export function read(d: Ds, x: any): unknown[] {
  const out: unknown[] = [];
  for (const s of SECTIONS) {
    out.push(d[s]);
    out.push(x[s]);
    out.push(Reflect.get(x, s));
  }
  return out;
}
