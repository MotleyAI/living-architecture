import { Storage } from './store';

export class CacheA {
  getDataset(name: string): number {
    return name.length;
  }
}

export class CacheB {
  getDataset(name: string): number {
    return name.length + 1;
  }
}

/** Calls `getDataset` on either cache. */
export function h(x: CacheA | CacheB, s: Storage): number {
  return x.getDataset('a') + s.getDataset('b');
}
