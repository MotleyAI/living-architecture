export class Ds {
  columns: string[] = [];
}

const SECTIONS = ['columns', 'fields'] as const;

export function read(d: Ds): unknown[] {
  return SECTIONS.map((s) => Reflect.get(d, s));
}
