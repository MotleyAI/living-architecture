import { legacy } from './api';

export function f(): object {
  const modern = 2;
  return { legacy, modern };
}
