import { Ds } from './m';

export function clear(d: Ds): void {
  for (const s of ['columns', 'name'] as const) {
    Reflect.set(d, s, null);
  }
}
