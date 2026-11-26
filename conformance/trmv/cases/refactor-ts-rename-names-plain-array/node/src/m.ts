export class Ds {
  columns: string[] = [];
}

const NAMES = ['columns'];

export function read(d: Ds): unknown[] {
  const out: unknown[] = [];
  for (const s of NAMES) {
    out.push(Reflect.get(d, s));
  }
  return out;
}
