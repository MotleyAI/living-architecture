import { C } from './c';

export function read(c: C): number {
  return c.old + c.value;
}
