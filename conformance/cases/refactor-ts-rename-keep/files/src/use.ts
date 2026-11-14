import { Storage } from './store';

export function f(s: Storage): number {
  return s.getDataset('a');
}

export function g(s: Storage): number {
  return s.getModel('b');
}
