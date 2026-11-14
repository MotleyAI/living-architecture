import { Storage } from './store';

export class CacheA {
  getModel(name: string): number {
    return name.length;
  }
}

export class CacheB {
  getModel(name: string): number {
    return name.length + 1;
  }
}

/** Calls `getModel` on either cache. */
export function h(x: CacheA | CacheB, s: Storage): number {
  return x.getModel('a') + s.getModel('b');
}
