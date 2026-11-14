import { Storage } from '../store';

export function f(s: Storage): number {
  return s.getModel('a');
}

export function g(s: Storage): number {
  return s.getModel('b');
}
