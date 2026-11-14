import { Store } from './store';

export function f(s: Store, pick: (key: string) => unknown): unknown[] {
  const slow = 'getModel is slow';
  return [pick('getModel'), pick(`getModel`), s['getModel']('a'), slow];
}
