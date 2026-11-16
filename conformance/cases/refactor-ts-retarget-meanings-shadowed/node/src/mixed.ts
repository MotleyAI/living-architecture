import type { Facade } from './core';
import { Flight } from './compat';

export const t: Facade | undefined = undefined;

export function make(): object {
  const Facade = 1;
  const typed: Flight | undefined = undefined;
  return [Facade, typed, new Flight()];
}
