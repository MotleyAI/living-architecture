import { legacy } from './api';

export { legacy };

export function make(): number {
  return legacy();
}
