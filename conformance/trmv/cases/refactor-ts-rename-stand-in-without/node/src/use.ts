import { ModelReadCache, StorageBackend } from './store';

export function f(s: StorageBackend, c: ModelReadCache): number {
  return s.getModel('a') + c.getModel('b');
}
