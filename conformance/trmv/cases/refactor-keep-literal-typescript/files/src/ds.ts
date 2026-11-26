export interface Ds {
  version?: number;
  fields: string[];
}

const version = 3;
const key = 'version';

export const a: Ds = { version: 3, columns: [] };
export const b: Ds = { 'version': 3, columns: [] };
export const c: Ds = { fields: [] };
export const d: Ds = { version, columns: [] };
export const e: Ds = { [key]: 3, fields: [] };
export const f: Ds = { ...{ version: 3 }, fields: [] };
export const g: { version: number; items: Ds[] } = { version: 1, items: [{ columns: [] }] };
export const h: { items: Ds[] } = { items: [{ version: 2, columns: [] }, { fields: [] }] };
