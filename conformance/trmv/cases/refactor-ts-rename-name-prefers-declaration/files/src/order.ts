import { foo } from './a';

export const viaImport = foo();

export function wrap(): number {
  const foo = 2;
  return foo;
}
