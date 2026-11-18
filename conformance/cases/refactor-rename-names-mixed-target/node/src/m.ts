export class Ds {
  columns: string[] = [];
}

export class Other {
  columns: number[] = [];
}

const SECTIONS = ['columns'] as const;

export function read(d: Ds, o: Other): unknown[] {
  const out: unknown[] = [];
  for (const s of SECTIONS) {
    out.push(d[s]);
    out.push(Reflect.get(o, s));
  }
  return out;
}
