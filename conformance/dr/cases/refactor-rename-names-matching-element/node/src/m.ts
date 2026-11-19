export class Ds {
  columns: string[] = [];
  label = '';
}

const FIELDS = ['label', 'columns'] as const;

export function read(d: Ds): unknown[] {
  const out: unknown[] = [];
  for (const f of FIELDS) {
    out.push(Reflect.get(d, f));
  }
  return out;
}
